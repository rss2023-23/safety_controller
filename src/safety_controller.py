#!/usr/bin/env python

import numpy as np
import sensor_msgs.point_cloud2 as pc2
import rospy
from std_msgs.msg import Float32
from rospy.numpy_msg import numpy_msg
from sensor_msgs.msg import LaserScan, PointCloud2
from ackermann_msgs.msg import AckermannDriveStamped
import laser_geometry.laser_geometry as lg
import math
from visualization_tools import *


class SafetyController:
    # ROS Parameters
    SCAN_TOPIC = rospy.get_param("safety_controller/scan_topic", "/scan")
    DRIVE_TOPIC = rospy.get_param("safety_controller/drive_topic", "/vesc/low_level/ackermann_cmd_mux/input/safety")

    # Tunable Parameters
    SCAN_STARTING_INDEX = rospy.get_param("safety_controller/scan_starting_index", 460)
    SCAN_ENDING_INDEX = rospy.get_param("safety_controller/scan_ending_index", 620)
    INTERCEPT = rospy.get_param("safety_controller/intercept", 0)
    MULTIPLIER = rospy.get_param("safety_controller/danger_threshold", 0.2335)
    EXPONENT = rospy.get_param("safety_controller/danger_threshold", 1.787)

    # Testing Parameters
    TESTING_VELOCITY = rospy.get_param("safety_controller/velocity", 2)
    IS_TESTING = rospy.get_param("safety_controller/is_testing", False)


    last_drive_command = None
    last_drive_speed = 1

    def __init__(self):
        # Subscribe to LIDAR Sensor
        rospy.Subscriber(self.SCAN_TOPIC, LaserScan, self.on_lidar_scan)

        # Subscribe to Driving Command
        rospy.Subscriber("/vesc/high_level/ackermann_cmd_mux/output", AckermannDriveStamped, self.on_drive_command)

        # Publish Car Actions
        self.car_publisher = rospy.Publisher(
            self.DRIVE_TOPIC, AckermannDriveStamped, queue_size=10)
        self.car_testing_publisher = rospy.Publisher(
            "/vesc/ackermann_cmd_mux/input/navigation", AckermannDriveStamped, queue_size=10)

        # Publish Rosbag Data
        self.data_logger = rospy.Publisher(
            "/safety_controller/data_logger", Float32, queue_size=10)

        # Handle Laser Geometry Projection
        self.laser_projector = lg.LaserProjection()
        self.laser_projection_publisher = rospy.Publisher(
            "laser_projection", PointCloud2, queue_size=1)

    def on_drive_command(self, drive_command):
        # Update driving command information
        if drive_command != None and drive_command.drive.speed != None:
            self.last_drive_command = drive_command
            self.last_drive_speed = drive_command.drive.speed


    def on_lidar_scan(self, lidar_data):
        """
        lidar_data:
        Number Samples: 1081
        Angle Increment: 0.00436332309619
        """
        # Get lidar data of collision zone
        collision_zone_data = self.get_collision_zone_data(lidar_data)
        collision_zone_distances = collision_zone_data.ranges
    
        # Visualize collision zone points
        wall_projection = self.laser_projector.projectLaser(collision_zone_data)
        self.laser_projection_publisher.publish(wall_projection)

        # Get Collision Zone Data
        min = np.min(collision_zone_distances)
        average = np.average(collision_zone_distances)

        # Test Safety Controller
        if self.IS_TESTING:
            self.data_logger.publish(min)
            self.drive_car()

        # Check for potential collision
        if self.last_drive_speed > 0 and min <= self.INTERCEPT + self.MULTIPLIER*(self.EXPONENT)**(self.last_drive_speed):
            rospy.loginfo("[WARNING]: Hault Command Issued by Safety Controller")
            self.stop_car() # Collision detected!

    def get_collision_zone_data(self, lidar_data):
        """
        Mutates lidar_data to only contain the lidar data in the collision zone of the car

        Collision Zone (cone of site in front of the car): SCAN_STARTING_INDEX to SCAN_ENDING_INDEX
        """
        lidar_data.ranges = lidar_data.ranges[self.SCAN_STARTING_INDEX:self.SCAN_ENDING_INDEX]
        old_min_angle = lidar_data.angle_min
        lidar_data.angle_min = old_min_angle + lidar_data.angle_increment * float(self.SCAN_STARTING_INDEX)
        lidar_data.angle_max = old_min_angle + lidar_data.angle_increment * float(self.SCAN_ENDING_INDEX-1)

        return lidar_data

    def stop_car(self):
        car_action_stamped = AckermannDriveStamped()

        # Make header
        car_action_stamped.header.stamp = rospy.Time.now()
        car_action_stamped.header.frame_id = "world"

        # Make command
        car_action = car_action_stamped.drive
        car_action.steering_angle = 0
        car_action.steering_angle_velocity = 0
        car_action.speed = -0.1
        car_action.acceleration = 0
        car_action.jerk = 0

        # Publish command
        self.car_publisher.publish(car_action_stamped)

    def drive_car(self):
        car_action_stamped = AckermannDriveStamped()

        # Make header
        car_action_stamped.header.stamp = rospy.Time.now()
        car_action_stamped.header.frame_id = "world"

        # Make command
        car_action = car_action_stamped.drive
        car_action.steering_angle = 0
        car_action.steering_angle_velocity = 0
        car_action.speed = self.TESTING_VELOCITY
        car_action.acceleration = 0
        car_action.jerk = 0

        # Publish command
        self.car_testing_publisher.publish(car_action_stamped)


if __name__ == "__main__":
    rospy.init_node('safety_controller')
    wall_follower = SafetyController()
    rospy.spin()
