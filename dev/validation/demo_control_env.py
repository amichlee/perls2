""" Class testing different controller functionality..
"""
from __future__ import division

import time
import math
import pybullet
import numpy as np
from perls2.utils.yaml_config import YamlConfig
from perls2.envs.env import Env

import gym.spaces as spaces


class DemoControlEnv(Env):
    """The class for Pybullet Sawyer Robot environments performing a reaching task.
    """
    def __init__(self,
                 config,
                 use_visualizer=False,
                 name=None,
                 use_abs=True,
                 test_fn='set_ee_pose'):
        """Initialize.

        Args:
            config (str, dict): A relative filepath to the config file. Or a
                parsed YamlConfig file as a dictionary.
                e.g. 'cfg/my_config.yaml'
            use_visualizer (bool): A flag for whether or not to use visualizer
            name (str): of the environment

                See documentation for more details about config files.
        """

        super().__init__(config, use_visualizer, name)
        self.use_abs = use_abs
        self.test_fn = test_fn

    def reset(self):
        self.episode_num += 1
        self.num_steps = 0
        self.world.reset()
        self.robot_interface.reset()
        # self.sensor_interface.reset()

        observation = self.get_observation()

    def get_observation(self):
        obs = {}
        obs['ee_pose'] = self.robot_interface.ee_pose
        obs['q'] = self.robot_interface.q
        obs['dq'] = self.robot_interface.dq

        return obs

    # def _exec_action(self, action):
    #     """Applies the given action to the simulation.

    #         Args: action (dict): dictionary of commands specific to test_fn to
    #             execute action.
    #     """
    #     if (self.robot_interface.controlType == 'EEImpedance' or
    #        (self.robot_interface.controlType == 'EEPosture')):
    #         # self.test_fn(action)
    #         # self.robot_interface.move_ee_delta(action)
    #         if self.test_fn == 'set_ee_pose':
    #             self.robot_interface.set_ee_pose(
    #                 delta=None, set_pos=action[:3], set_ori=action[3:])
    #         if self.test_fn == 'move_ee_delta':
    #             self.robot_interface.move_ee_delta(
    #                 delta=action, set_pos=None, set_ori=None)
    #     elif self.robot_interface.controlType == 'JointVelocity':
    #         self.robot_interface.set_joint_velocity(action)
    #     elif self.robot_interface.controlType == 'JointImpedance':
    #         self.robot_interface.set_joint_delta(delta=action)
    #         # self.robot_interface.set_joint_positions(action)
    #     elif self.robot_interface.controlType == 'JointTorque':
    #         self.robot_interface.set_joint_torque(action)
    #     self.robot_interface.action_set = True

    def _exec_action(self, action_kw):
        """Applies the given action to the simulation.

            Args: action_kw (dict): dictionary of commands specific to test_fn to
                execute action.
        """

        if (self.robot_interface.controlType == 'EEImpedance' or
           (self.robot_interface.controlType == 'EEPosture')):
            # self.test_fn(action)
            # self.robot_interface.move_ee_delta(action)
            if self.test_fn == 'set_ee_pose':
                self.robot_interface.set_ee_pose(
                    **action_kw)
            if self.test_fn == 'move_ee_delta':
                self.robot_interface.move_ee_delta(
                    **action_kw)
        elif self.robot_interface.controlType == 'JointVelocity':
            self.robot_interface.set_joint_velocity(action)
        elif self.robot_interface.controlType == 'JointImpedance':
            self.robot_interface.set_joint_delta(delta=action)
            # self.robot_interface.set_joint_positions(action)
        elif self.robot_interface.controlType == 'JointTorque':
            self.robot_interface.set_joint_torque(action)
        self.robot_interface.action_set = True

    def rewardFunction(self):
        return None