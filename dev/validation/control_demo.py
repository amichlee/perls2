from demo_control_env import DemoControlEnv
import numpy as np
import time
import logging
from datetime import datetime
import argparse
import matplotlib.pyplot as plt

import perls2.controllers.utils.control_utils as C
import perls2.controllers.utils.transform_utils as T


class Demo():
    """Class definition for demonstration.
        Demonstrations are a series of actions that follow a specified pattern
        and are of appropriate dimension for the controller.

        Attributes:
        env (DemoControlEnv): environment to step with action generated
            by demo.
        ctrl_type (str): string identifying type of controller:
            EEPosture, EEImpedance, JointImpedance, JointTorque
        demo_type (str): type of demo to perform (zero, line, sequential,
            square.)

    """
    def __init__(self, ctrl_type, demo_type, test_fn,  use_abs=True, **kwargs):
        self.env = DemoControlEnv('dev/validation/demo_control_cfg.yaml',
                                  use_visualizer=True,
                                  use_abs=use_abs,
                                  test_fn=test_fn,
                                  name='Demo Control Env')
        print("initializing")
        self.ctrl_type = ctrl_type
        self.env.robot_interface.change_controller(self.ctrl_type)
        self.demo_type = demo_type
        self.use_abs = use_abs
        self.test_fn = test_fn
        self.plot_pos = kwargs['plot_pos']
        self.plot_error = kwargs['plot_error']
        self.save_fig = kwargs['save_fig']
        self.save = kwargs['save']
        self.demo_name = kwargs['demo_name']
        if self.demo_name is None:
            self.demo_name = "{}_{}_{}".format("0915",self.ctrl_type, self.demo_type)

        # Initialize lists for storing data.
        self.errors = []
        self.actions = []
        self.states = []
        self.world_type = self.env.config['world']['type']
        self.initial_pose = self.env.robot_interface.ee_pose

    def get_action_list(self):
        raise NotImplementedError

    def run(self):
        raise NotImplementedError

    def save_data(self):
        fpath = "dev/validation/{}.npz".format(self.demo_name)
        np.savez(fpath, states=self.states,
                 errors=self.errors, actions=self.actions,
                 goals=self.goal_states, allow_pickle=True)

    def get_goal_state(self, delta):
        raise NotImplementedError

    def make_demo(**kwargs):
        """Factory method for making the write demo per params.
        """
        if kwargs['ctrl_type'] in ["EEImpedance", "EEPosture"]:
            return OpSpaceDemo(**kwargs)
        elif kwargs['ctrl_type'] in ["JointImpedance"]:
            return JointSpaceDeltaDemo(**kwargs)


class JointSpaceDemo(Demo):

    """Class definition for joint space demonstrations.

    Joint space demonstrations are 7 dof for each motor.
    They include joint positions, velocities and torques.

    Attributes:
        delta_val (float): magnitude of delta from current position.
            Absolute joint space demos are also determined by adding
            this delta to current joint position.
    """
    def __init__(self, ctrl_type, demo_type, use_abs=False,
                 delta_val=0.05, num_steps=10, test_fn='set_joint_delta',
                 **kwargs):
        super().__init__(ctrl_type, demo_type, use_abs, test_fn, **kwargs)
        # Get goal states based on demo and control type.
        self.start_pos = self.env.robot_interface.q
        self.delta_val = delta_val
        self.goal_states = []
        self.action_list = self.get_action_list()
        self.goal_states = self.get_goal_states()
        self.num_steps = len(self.action_list)
        self.step_num = 0

    def get_state(self):
        return self.env.robot_interface.q[:7]

    def run(self):
        """Run the demo. Execute actions in sequence and calculate error.
        """
        print("Running {} demo \n with control type {}.\n Test \
            function {}".format(self.ctrl_type, self.demo_type, self.test_fn))

        print("Joint Pose initial{}".format(self.env.robot_interface.q))
        for i, action in enumerate(self.action_list):
            print("Action:\t{}".format(action))
            self.env.step(action, time.time())
            self.actions.append(action)
            new_state = self.get_state()
            print("q Pos:\t{}".format(self.env.robot_interface.q))
            print("goal state:\t{}".format(self.goal_states[i+1]))
            self.states.append(new_state)
            self.errors.append(
                self.compute_error(self.goal_states[i+1], new_state))
            print(self.errors[-1])

        self.env.robot_interface.disconnect()


class JointSpaceDeltaDemo(JointSpaceDemo):

    def get_goal_states(self):
        goal_states = [self.start_pos]
        for action in self.action_list:
            goal_states.append(np.add(goal_states[-1], action))
        return goal_states

    def get_action_list(self):
        """ Get action list for random demo.

            Each action will move only one joint in a random direction
            at a time. the magnitude of each action is determined by
            the delta_val.

            e.g.
            [0, -0.05, 0, 0, 0, 0]

        """
        # Joint position delta demo.

        NUM_JOINTS = 7
        joint_position_delta_demo = [np.zeros(NUM_JOINTS)]
        # Move each joint individually by +0.05 radians
        for joint_num in range(NUM_JOINTS):
            delta = np.zeros(NUM_JOINTS)
            delta[joint_num] = self.delta_val
            joint_position_delta_demo.append(delta)

        # Move each joint individually by -0.05 radians
        for joint_num in range(NUM_JOINTS):
            delta = np.zeros(NUM_JOINTS)
            delta[-1 - joint_num] = -self.delta_val
            joint_position_delta_demo.append(delta)

        return joint_position_delta_demo

    def compute_error(self, goal, current):
        return np.subtract(goal, current)


class JointSpaceAbsDemo(JointSpaceDeltaDemo):
    def __init__(self, ctrl_type, demo_type, use_abs, start_pos):
        self.start_pos = start_pos
        super().__init__(ctrl_type, demo_type, use_abs)

    def get_action_list(self):
        """Add actions to joint position and update to get
        absolute positions at each step.
        """

        jp_delta_demo = super().get_action_list()
        jp_abs_demo = []

        for action in jp_abs_demo:
            jp_abs_demo.append(self.states, jp_delta_demo)
            self.start_pos = jp_abs_demo[-1]
        return jp_abs_demo


class OpSpaceDemo(Demo):
    """ Demos for testing operational space control. These include
    End-Effector Imedance, and End-Effector with nullspace posture control.
    """
    def __init__(self, ctrl_type, demo_type, use_abs=False,
                 path_length=0.15, delta_val=None, num_steps=50, test_fn='set_ee_pose',
                 fix_ori=True, fix_pos=False, **kwargs):
        """
        ctrl_type (str): string identifying type of controller:
            EEPosture, EEImpedance, JointImpedance, JointTorque
        demo_type (str): type of demo to perform (zero, line, sequential,
            square.)
        """
        super().__init__(ctrl_type=ctrl_type, demo_type=demo_type, use_abs=use_abs,
                         test_fn=test_fn, **kwargs)
        self.initial_pose = self.env.robot_interface.ee_pose
        self.delta_val = delta_val
        self.path_length = path_length
        self.num_steps = num_steps
        self.goal_poses = self.get_goal_poses()
        # self.action_list = self.get_action_list()
        self.goal_states = self.get_goal_states()
        self.fix_ori = fix_ori
        self.fix_pos = fix_pos

        # self.print_name = "Demo_{}_{}_{}_{}".format()

    def run(self):
        """Run the demo. Execute actions in sequence and calculate error.
        """
        print("Running {} demo \n with control type {}.\n \
            Test function {}".format(
            self.ctrl_type, self.demo_type, self.test_fn))

        print("EE Pose initial{}\n".format(self.env.robot_interface.ee_pose))
        print("--------")
        for i, goal_pose in enumerate(self.goal_poses):
            action= self.get_action(goal_pose, self.get_state())
            action_kwargs = self.get_action_kwargs(action)
            #action_kw = self.get_action_kwargs(action)
            print("Action:\t{}".format(action[:3]))
            self.env.step(action_kwargs, time.time())
            self.actions.append(action)
            new_state = self.get_state()
            print("EE Pose:\t{}".format(self.env.robot_interface.ee_pose[:3]))
            self.states.append(new_state)
            self.errors.append(
                self.compute_error(self.goal_poses[i], new_state))
            print("ori_error\t{}".format(self.errors[-1][3:]))
            #input("Press Enter to continue")

        self.env.robot_interface.disconnect()
        if self.plot_error:
            self.plot_errors()
        if self.plot_pos:
            self.plot_positions()

        if self.save:
            self.save_data()


    def get_action(self, goal_pose, current_pose):
        if self.test_fn =="move_ee_delta":
            action = get_delta(goal_pose, current_pose)
        elif self.test_fn =="set_ee_pose":
            action = goal_pose
        else:
            raise ValueError("invalid test fn")
        return action

    def get_action_kwargs(self, action):
        """Return tuple of action and dict of kwargs specific to function being tested.

        Args:
            action (list): action to be converted in kwargs for robot_interface functions.
        Returns
            action_kwargs (dict): dictionary with key-value pairs corresponding to
                arguments for robot_interface command being tested.
        """
        action_kwargs  = {}
        if self.test_fn =="move_ee_delta":
            action_kwargs['delta'] = action
            action_kwargs['set_pos'] = None
            action_kwargs['set_ori'] = None
            if self.fix_ori:
                action_kwargs['set_ori'] = self.goal_pose[3:]
            if self.fix_pos:
                action_kwargs['set_pos'] = self.goal_pose[:3]
        if self.test_fn=="set_ee_pose":
            action_kwargs['delta'] = None
            action_kwargs['set_pos'] = action[:3]
            action_kwargs['set_ori'] = action[3:]

        return action_kwargs

    def get_action_list(self):
        """Get the set of actions based on the type of the demo,
        """

        if self.demo_type == "Zero":
            self.path = Line(start_pose=self.initial_pose,
                             num_pts=self.num_steps,
                             delta_val=0,
                             path_length=0)

        elif self.demo_type == "Square":
            self.path = Square(start_pose=self.initial_pose,
                               side_num_pts=int(self.num_steps/4),
                               delta_val=self.delta_val)
        elif self.demo_type == "Line":
            self.path = Line(start_pose=self.initial_pose,
                             num_pts=self.num_steps,
                             delta_val=self.delta_val,
                             path_length=self.path_length)

        elif self.demo_type == "Rotation":
            self.path = Rotation(
                start_pose=self.initial_pose,
                num_pts=self.num_steps,
                delta_val=self.delta_val)
        else:
            raise ValueError("Invalid Demo type")

        if self.test_fn=="set_ee_pose":
            action_list = self.path.path
        elif self.test_fn=="move_ee_delta":
            action_list = self.path.deltas
        else:
            raise ValueError("Invalid test_fn")
        return action_list

    def get_goal_poses(self):
        """ Get a list of absolute end_effector states
        """
        if self.demo_type == "Zero":
            self.path = Line(start_pose=self.initial_pose,
                             num_pts=self.num_steps,
                             delta_val=0,
                             path_length=0)
        elif self.demo_type == "Square":
            self.path = Square(start_pose=self.initial_pose,
                               side_num_pts=int(self.num_steps/4),
                               delta_val=self.delta_val)
        elif self.demo_type == "Line":
            self.path = Line(start_pose=self.initial_pose,
                             num_pts=self.num_steps,
                             delta_val=self.delta_val,
                             path_length=self.path_length)

        elif self.demo_type == "Rotation":
            self.path = Rotation(
                start_pose=self.initial_pose,
                num_pts=self.num_steps,
                delta_val=self.delta_val)
        else:
            raise ValueError("Invalid Demo type")

        goal_poses = self.path.path
        return goal_poses

    def get_goal_states(self):
        """ Get goal states based on the demo type and action list.

        For Zero goal states with use_abs, goal states are just
        copied initial end-effector pose.
        """
        if self.path is not None:
            goal_states = self.path.path

        else:
            raise ValueError("Get actions list before goal states")

        return goal_states

    def get_state(self):
        """ Proprio state for robot we care about for this demo: ee_pose.
        Used to compute error.
        """
        return self.env.robot_interface.ee_pose

    def compute_error(self, goal_state, new_state):
        """ Compute the error between current state and goal state.
        For OpSpace Demos, this is position and orientation error.
        """
        goal_pos = goal_state[:3]
        new_pos = new_state[:3]
        # Check or convert to correct orientation
        goal_ori = T.convert_euler_quat_2mat(goal_state[3:])
        new_ori = T.convert_euler_quat_2mat(new_state[3:])

        pos_error = np.subtract(goal_pos, new_pos)
        ori_error = C.orientation_error(goal_ori, new_ori)

        return np.hstack((pos_error, ori_error))

    def plot_sequence_arrows(self, axes, x, y, color):
        """Plot a sequence of arrows given a list of x y points.
        """
        for pt_idx in range(len(x)-1):
            dx = np.subtract(x[pt_idx+1], x[pt_idx])
            dy = np.subtract(y[pt_idx+1], y[pt_idx])

            axes.arrow(x[pt_idx], y[pt_idx], dx, dy, color=color)

    def plot_positions(self):
        """ Plot 3 plots showing xy, xz, and yz position.
        Helps for visualizing decoupling.
        """

        goal_x = [goal[0] for goal in self.goal_states]
        goal_y = [goal[1] for goal in self.goal_states]
        goal_z = [goal[2] for goal in self.goal_states]

        state_x = [state[0] for state in self.states]
        state_y = [state[1] for state in self.states]
        state_z = [state[2] for state in self.states]

        fig, (ax_xy, ax_xz, ax_yz) = plt.subplots(1, 3)

        ax_xy.plot(goal_x, goal_y, 'or')
        ax_xy.plot(state_x, state_y, '*b')
        # self.plot_sequence_arrows(ax_xy, state_x, state_y, 'b')
        ax_xy.set_xlabel("x position (m)")
        ax_xy.set_ylabel("y position (m)")
        ax_xy.set_ylim(bottom=-0.1, top=0.4)
        ax_xy.set_xlim(left=0.35, right=0.75)

        ax_xz.plot(goal_x, goal_z, 'or')
        ax_xz.plot(state_x, state_z, '*b')
        ax_xz.set_xlabel("x position (m)")
        ax_xz.set_ylabel("z position (m)")
        ax_xz.set_ylim(bottom=-0.5, top=0.5)
        ax_xz.set_xlim(left=0.35, right=0.75)

        ax_yz.plot(goal_y, goal_z, 'or')
        ax_yz.plot(state_y, state_z, '*b')
        ax_yz.set_xlabel("y position (m)")
        ax_yz.set_ylabel("z position(m)")
        ax_yz.set_ylim(bottom=0, top=2.0)
        ax_yz.set_xlim(left=-0.5, right=0.5)
        plt.show()

    def plot_errors(self):
        """ Plot 6 plots showing errors for each dimension.
        x, y, z and qx, qy, qz euler angles (from C.orientation_error)
        """
        errors_x = [error[0] for error in self.errors]
        errors_y = [error[1] for error in self.errors]
        errors_z = [error[2] for error in self.errors]

        errors_qx = [error[3] for error in self.errors]
        errors_qy = [error[4] for error in self.errors]
        errors_qz = [error[5] for error in self.errors]

        fig, ((e_x, e_y, e_z), (e_qx, e_qy, e_qz)) = plt.subplots(2, 3)

        e_x.plot(errors_x)
        e_x.set_title("X error per step.")
        e_x.set_ylabel("error (m)")
        e_x.set_xlabel("step num")

        e_y.plot(errors_y)
        e_y.set_ylabel("error (m)")
        e_y.set_xlabel("step num")
        e_y.set_title("y error per step")

        e_z.plot(errors_z)
        e_z.set_title("z error per step.")
        e_z.set_ylabel("error (m)")
        e_z.set_xlabel("step num")

        e_qx.plot(errors_qx)
        e_qx.set_title("qx error per step.")
        e_qx.set_ylabel("error (rad)")
        e_qx.set_xlabel("step num")

        e_qy.plot(errors_qy)
        e_qy.set_title("qy error per step.")
        e_qy.set_ylabel("error (rad)")
        e_qy.set_xlabel("step num")

        e_qz.plot(errors_qz)
        e_qz.set_title("qz error per step.")
        e_qz.set_ylabel("error (rad)")
        e_qz.set_xlabel("step num")

        plt.show()

def get_delta(goal_pose, current_pose):
    """Get delta between goal pose and current_pose.

    Args: goal_pose (list): 7f pose [x, y, z, qx, qy, qz, w] . Position and quaternion of goal pose.
          state (list): 7f Position and quaternion of current pose.

    Returns: delta (list) 6f [dx, dy, dz, ax, ay, az] delta position and delta orientation
        as axis-angle.
    """

    if len(goal_pose) != 7:
        raise ValueError("Goal pose incorrect dimension should be 7f")
    if len(current_pose) !=7:
        raise ValueError("Current pose incorrect dimension, should be 7f")

    dpos = np.subtract(goal_pose[:3], current_pose[:3])
    goal_mat = T.quat2mat(goal_pose[3:])
    current_mat = T.quat2mat(current_pose[3:])
    delta_mat_T = np.dot(goal_mat, current_mat.T)
    delta_quat = T.mat2quat(np.transpose(delta_mat_T))
    delta_aa = T.quat2axisangle(delta_quat)

    return np.hstack((dpos, delta_aa)).tolist()

def apply_delta(pose, delta):
    """ Applies delta to pose to obtain new 7f pose.
    Args: pose (7f): x, y, z, qx, qy, qz, w . Position and quaternion
          delta (6f): dx, dy, dz, ax, ay, az. delta position and axis-angle

    """
    if len(delta) != 6:
        raise ValueError("delta should be [x, y, z, ax, ay, az]. Orientation should be axis-angle")
    if len(pose) != 7:
        raise ValueError("pose should be [x, y, z, qx, qy, qz, w] Orientation should be quaternion.")
    pos = pose[:3]
    dpos = delta[:3]

    # Get current orientation and delta as matrices to apply 3d rotation.
    ori_mat = T.quat2mat(pose[3:])
    delta_quat = T.axisangle2quat(delta[3:])
    delta_mat = T.quat2mat(delta_quat)
    new_ori = np.dot(delta_mat.T, ori_mat)

    # convert new orientation to quaternion.
    new_ori_quat = T.mat2quat(new_ori)

    # add dpos to current position.
    new_pos = np.add(pos, dpos)

    return np.hstack((new_pos, new_ori_quat))

class Path():
    """Class definition for path definition (specific to ee trajectories)

    A Path is a series

    """

    def __init__(self, shape, num_pts):
        self.shape = shape
        self.num_pts = num_pts
        self.path = []

    def make_path(self):
        self.path = [self.start_pose]
        for delta in self.deltas:
            new_pose = apply_delta(self.path[-1], delta)
            # self.path.append(np.add(self.path[-1], delta))
            self.path.append(new_pose)

        # Append path to the same
        for _ in range(int(0.2*self.num_pts)):
            self.path.append(self.path[-1])


def make_simple_rot_mat(angle=np.pi/4):
    """Make a simple rotation matrix, rotating about one axis.
    """
    rot_m = np.eye(3)
    rot_m[0, 0] = np.cos(angle)
    rot_m[0, 1] = -np.sin(angle)
    rot_m[0, 2] = 0
    rot_m[1, 0] = np.sin(angle)
    rot_m[1, 1] = np.cos(angle)
    rot_m[1, 2] = 0
    rot_m[2, 0] = 0
    rot_m[2, 1] = 0
    rot_m[2, 2] = 1
    return rot_m

class Rotation(Path):
    """ Class definition for path that rotating end effector in place.
    Start and end orientation should be in euler angles.
    """
    def __init__(self, start_pose, num_pts,
                 rotation_rad=np.pi/4, delta_val=None, dim=2, end_ori=None):
        print("Making Rotation Path")
        self.start_pose = start_pose
        self.end_ori = end_ori
        self.num_pts = num_pts
        self.rotation_rad = rotation_rad
        if delta_val is None:
            delta_val = np.divide(rotation_rad, num_pts)
            print("delta_val\t{}".format(delta_val))
        self.dim = dim
        self.delta_val = delta_val
        self.get_deltas()
        self.path = []
        self.make_path()

    def get_deltas(self):
        """Convert euler angle rotation with magnitude delta in the direction
        specified by dim.
        """
        delta = np.zeros(3)
        delta[self.dim] = self.delta_val
        # pad with position deltas= 0
        delta = np.hstack(([0, 0, 0], delta))
        self.deltas = [delta]*self.num_pts

class Line(Path):
    """Class definition for straight line in given direction.
    """
    def __init__(self, start_pose, num_pts, path_length,
                 delta_val=None, dim=0, end_pos=None):
        """ Initialize Line class

        Args:
            start_pos (list): 7f pose at start of path. Best to
                set at robot reset pose.
            num_pts (int): number of points in path.
            length (float): length of path in m
            delta_val (float): (optional) delta in m between
                each step. If None, end_pos must be specified.
            dim (int): direction to move for line, x = 0, y=1,
                z=2.
            end_pos (list): (optional) end pose for path. If not
                None, dim, and delta_val are ignored. Straight
                Line is interpolated between start and end_pos.

        """
        self.start_pose = start_pose
        self.num_pts = num_pts
        self.path_length = path_length
        if delta_val is None:
            delta_val = np.divide(self.path_length, self.num_pts)
        self.delta_val = delta_val
        self.dim = dim
        self.deltas = []
        self.get_deltas()
        self.path = []
        self.make_path()

    def get_deltas(self):

        delta = np.zeros(6)
        delta[self.dim] = self.delta_val
        self.deltas = [delta]*self.num_pts
        # self.deltas[0] = np.zeros(7)


class Square(Path):
    """Class def for square path.

    Square path defined by side length and start point.
    At step 4 * sidelength -1, ee is not at initial point.
    Last step returns to initial point.

    Square path is ordered in clockwise from origin (Bottom, Left, Top, Right)

    Attributes:
        start_pos (3f): xyz start position to begin square from.
        side_num_pts (int): number of steps to take on each side.
            (not counting start.)
        delta_val (float): step size in m to take for each step.
        deltas (list): list of delta xyz from a position to reach next position
             on path.
        path (list): list of actions to take to perform square path. Actions
            are either delta xyz from current position (if use_abs is False) or
            they are absolute positions taken by adding the deltas to start.

    """
    def __init__(self, start_pose, side_num_pts, delta_val):

        self.start_pose = start_pose
        self.num_pts = side_num_pts
        self.delta_val = delta_val
        self.deltas = []
        self.get_deltas()
        self.path = []
        self.make_path()

    def get_deltas(self):
        """ Get a series of steps from current position that produce
        a square shape. Travel starts with bottom side in positive direction,
        then proceeds clockwise (left, top, right.)

        """
        self.deltas = [[0, 0, 0, 0, 0, 0]]
        # Bottom side.
        for pt in range(self.num_pts):
            self.deltas.append([self.delta_val, 0.0, 0.0, 0.0, 0.0, 0.0])
        # Left Side
        for pt in range(self.num_pts):
            self.deltas.append([0.0, -self.delta_val, 0.0, 0.0, 0.0, 0.0])
        # Top side
        for pt in range(self.num_pts):
            self.deltas.append([-self.delta_val, 0.0, 0.0, 0.0, 0.0, 0.0])
        # Right side
        for pt in range(self.num_pts):
            self.deltas.append([0.0, self.delta_val, 0.0, 0.0, 0.0, 0.0])