#!/usr/bin/env python  
import rospy
import tf
import numpy as np
import cv2
from cv_bridge import CvBridge, CvBridgeError
from std_msgs.msg import Int32MultiArray as vec
from sensor_msgs.msg import CameraInfo 
from sensor_msgs.msg import Image
from image_geometry import PinholeCameraModel
from gui import *
import copy
from cnn import *
from std_msgs.msg import String
#from compute_tf.msg import command

cam_model = PinholeCameraModel()
intrinsic_mat = np.zeros((3,3))
M = np.zeros((3,3))
M2 = np.zeros((3,3))
plane = []
result_array = []
print_array = []

bridge = CvBridge()
br = tf.TransformBroadcaster()
rot = []
point = []
axis = []
hand_pose_flag = 0

def send_command(index = 0,operation = 'hello project fukushima'):
	msg = str(index) + operation
	pub.publish(msg)
	print("command sent once")	
	send_success = True
	

def cal(xyz,plane):
    a,b,c,d = plane
    x,y,z = xyz
    k = -d/(a*x + b*y + c*z)
    return k*x,k*y,k*z
    #result_array

def qv_mult(q1, v1):
    v1 = tf.transformations.unit_vector(v1)
    q2 = list(v1)
    q2.append(0.0)
    return tf.transformations.quaternion_multiply(
        tf.transformations.quaternion_multiply(q1, q2), 
        tf.transformations.quaternion_conjugate(q1)
    )[:3]

def normalize(v):
    norm = np.linalg.norm(v)
    if norm == 0: 
       return v
    return v / norm

def callback2(data):
	global result_array
	global plane
	global print_array
	global rot
	global M
	global M2
	#rospy.loginfo("object_center %s",data.data)
	size = len(data.data)
	result_array = []
	print_array = []
	batch = 9
	for i in range(size/batch): 
		pixel_point = data.data[i*batch:(i+1)*batch]
		index = pixel_point[0]
		
		center = [int((pixel_point[1] + pixel_point[7])/2),int((pixel_point[2] + pixel_point[8])/2)]
		
		xyz = cam_model.projectPixelTo3dRay(center) #pixel points
		x,y,z = cal(xyz,plane) #calculate the 3d points
		result_array.append(index)
		result_array.append(x)
		result_array.append(y)
		result_array.append(z)

		top_left = [int(pixel_point[1]),int(pixel_point[2])]
		top_right = [int(pixel_point[3]),int(pixel_point[4])]
		bot_left = [int(pixel_point[5]),int(pixel_point[6])]
		bot_right = [int(pixel_point[7]),int(pixel_point[8])]

		top_middle = [int((top_left[0] + top_right[0])/2),int((top_left[1] + top_right[1])/2)]
		right_middle = [int((top_right[0] + bot_right[0])/2),int((bot_right[1] + bot_right[1])/2)]

		top_middle_xyz = cam_model.projectPixelTo3dRay(top_middle) 
		tm_x,tm_y,tm_z = cal(top_middle_xyz,plane) 
		right_middle_xyz = cam_model.projectPixelTo3dRay(right_middle) 
		rm_x,rm_y,rm_z = cal(right_middle_xyz,plane)

		x_axis = normalize(np.array([rm_x - x,rm_y -y,rm_z - z,0]))
		y_axis = normalize(np.array([tm_x - x,tm_y -y,tm_z - z,0]))
		z_axis = normalize(np.array([plane[0],plane[1],plane[2],0]))
		ones = np.array([0,0,0,1])
		rot_mat = np.vstack((x_axis,y_axis))
		rot_mat = np.vstack((rot_mat,z_axis))
		rot_mat = np.vstack((rot_mat,ones))
		
		#print(index)
		#print(rot_mat)
		#print('*'* 20)
		quat = tf.transformations.quaternion_from_matrix(rot_mat)
		quat /= np.linalg.norm(quat)
		
		off_set_x,off_set_y = individual_offset(top_left,top_right,bot_left,bot_right,center,index)
		refined_center = [center[0] + off_set_x,center[1] + off_set_y]
		refined_xyz = cam_model.projectPixelTo3dRay(refined_center) 
		refined_x,refined_y,refined_z = cal(refined_xyz,plane) 
		br.sendTransform((refined_x,refined_y,refined_z),(quat[0],quat[1],quat[2],quat[3]),rospy.Time.now(),"switch%d"%index,"camera_rgb_optical_frame")

		if(index == 4):
			off_set_x,off_set_y = individual_offset(top_left,top_right,bot_left,bot_right,center,index + 1)
			refined_center = [center[0] + off_set_x,center[1] + off_set_y]
			refined_xyz = cam_model.projectPixelTo3dRay(refined_center) 
			refined_x,refined_y,refined_z = cal(refined_xyz,plane) 
			br.sendTransform((refined_x,refined_y,refined_z),(quat[0],quat[1],quat[2],quat[3]),rospy.Time.now(),"switch%d"%(index + 1),"camera_rgb_optical_frame")
	
		local_arr = []
		local_arr.append(index)
		local_arr.append(top_left[0])
		local_arr.append(top_left[1])
		local_arr.append(top_right[0])
		local_arr.append(top_right[1])
		local_arr.append(bot_left[0])
		local_arr.append(bot_left[1])
		local_arr.append(bot_right[0])
		local_arr.append(bot_right[1])
		print_array.append(local_arr)
    
		if(index == 4):
			M = calculate_M(top_left,top_right,bot_left,bot_right)
		if(index == 2):
			M2 = calculate_M(top_left,top_right,bot_left,bot_right)

def send_frame_based_on_other(base,x_offset,y_offset,z_offset,rot,name,base_name):
	global axis
	x_axis,y_axis,z_axis = axis
	res = base + z_axis*z_offset + x_axis*x_offset + y_axis*y_offset
	br.sendTransform((res[0],res[1],res[2])
	,(rot[0],rot[1],rot[2],rot[3]),rospy.Time.now(),name,base_name)

def callback(data):
    global intrinsic_mat
    cam_model.fromCameraInfo(data)
    intrinsic_mat = cam_model.fullIntrinsicMatrix()

def plane_func(rot,trans):
	global axis
	global M
	y_axis = np.array([0,1,0])
	x_axis = np.array([1,0,0])
	z_axis = np.array([0,0,1])
	aruco_y = qv_mult(rot, y_axis)
	aruco_x = qv_mult(rot, x_axis)
	aruco_z = qv_mult(rot, z_axis)	
	a = aruco_z[0]
	b = aruco_z[1]
	c = aruco_z[2]
	x = trans[0]
	y = trans[1]
	z = trans[2]
	d = 0 - a*x - b*y - c*z
	xyz = [x,y,z]
	axis = [aruco_x,aruco_y,aruco_z]
	return [a,b,c,d]

def img_callback(data):
	global result_array
	global print_array
	global rot
	global M
	global M2
	global hand_pose_flag
	try:
		cv_image = bridge.imgmsg_to_cv2(data,"bgr8")
		hand_pose_flag,cmd,buttom,operation = updateView(cv_image, print_array,M,M2,model)
		if cmd:
			send_command(buttom,operation)
	except CvBridgeError as e: 
		print(e)
	

def calculate_M(top_left,top_right,bot_left,bot_right):
	global point
	
	points = np.array([(107 , 17), (481 , 13), (124, 435), (514, 407)])
	dst_pts = np.float32(points[:, np.newaxis, :])
	points2 = np.array([(top_left[0], top_left[1]), (top_right[0], top_right[1]), (bot_left[0], bot_left[1]), (bot_right[0], bot_right[1])])
	src_pts = np.float32(points2[:, np.newaxis, :])
	#print(points2) # calibration use
	Ml, mask = cv2.findHomography(src_pts, dst_pts, 0)
	#print(M)
	return Ml
	'''
	offset = 0.1
	try:
		x,y,z = xyz
		x_axis,y_axis,z_axis = axis
		base = np.array([x,y,z])
		points = np.array([(356, 118), (367, 16), (233, 103), (252, 3)])
		dst_pts = np.float32(points[:, np.newaxis, :])
		#print(z_axis)
		center = intrinsic_mat.dot(np.array([x,y,z]))
		x_end = intrinsic_mat.dot(base + x_axis*offset)
		y_end = intrinsic_mat.dot(base + y_axis*offset)
		xy_end = intrinsic_mat.dot(base + y_axis*offset + x_axis*offset)

		center = center * ( 1.0 /center.item(0,2) )
		x_end = x_end * ( 1.0 /x_end.item(0,2) )
		y_end = y_end * ( 1.0 /y_end.item(0,2) )
		xy_end = xy_end * ( 1.0 /xy_end.item(0,2) )

		point = [ (int(round(center.item(0,0))),int(round(center.item(0,1)))),
				  (int(round(x_end.item(0,0))),int(round(x_end.item(0,1)))),
				  (int(round(y_end.item(0,0))),int(round(y_end.item(0,1)))),
				  (int(round(xy_end.item(0,0))),int(round(xy_end.item(0,1))))
				]
		#print(point) #for calibration
		p_ = np.array(point)
		src_pts = np.float32(p_[:, np.newaxis, :])
		M, mask = cv2.findHomography(src_pts, dst_pts, 0)
		#print(M)

	except Exception as e: print(e)
	'''
class hand_initializer():
	def __init__(self):
		self.counter = 0
		self.trans = [0,0,0]
		self.rot = [0,0,0,0]
		self.adding = 0
		self.empty = 1
	def call(self,trans,rot,flag):
		if flag == 0:
			if self.adding == 0:
				if self.empty == 0:
					br.sendTransform(self.trans,self.rot,rospy.Time.now(),"hand","camera_rgb_optical_frame")
			else:
				self.adding = 0;
				for i in range(0,len(trans)):
					self.trans[i] /= self.counter
				for i in range(0,len(rot)):
					self.rot[i] /= self.counter
				self.counter = 0
				print(self.trans,self.rot)
				print('*' * 50)
				print(trans,rot)
		else:
			self.empty = 0
			if self.adding == 0:
				self.trans = [0,0,0]
				self.rot = [0,0,0,0]
				self.adding = 1
			else:
				self.counter += 1
				#self.trans += trans
				#self.rot += rot
				for i in range(0,len(trans)):
					self.trans[i] += trans[i]
				for i in range(0,len(rot)):
					self.rot[i] += rot[i]
		

if __name__ == '__main__': 
	global plane
	global rot
	global hand_pose_flag
	global pub
	global sess
	global model
	print("start")
	tsf.reset_default_graph()
	sess = tsf.Session()
	path = '/home/tommy/catkin_ws/src/compute_tf/src/'
	shape_x = 80
	shape_y = 180
	lr = 1e-3
	#restoreModel(sess, saver1, path + "model/model.ckpt")
	optimizer = tsf.train.AdamOptimizer(lr)
	model = CNNModel(shape_x, shape_y, sess, optimizer)
	saver1 = tsf.train.Saver()
	restoreModel(sess, saver1, path + "model/model.ckpt")

	hand = hand_initializer()
	cv2.namedWindow('interactive')
	cv2.setMouseCallback('interactive',position)
	rospy.init_node('aruco_tf_listener')
	listener = tf.TransformListener()
	rate = rospy.Rate(10.0)
	rospy.Subscriber("/camera/rgb/camera_info",CameraInfo,callback)
	rospy.Subscriber("/object_center", vec, callback2)
	rospy.Subscriber("/camera/rgb/image_color", Image, img_callback)
	pub = rospy.Publisher('command', String)
	counter = 0
	while not rospy.is_shutdown():
		counter += 1
		#if (counter % 50 == 0):
		#	send_command(operation = str(counter))
		try:
			(trans,rot) = listener.lookupTransform('/camera_rgb_optical_frame','/aruco_marker_frame', rospy.Time(0))
			#print(rot)
			#print(trans)
			plane = plane_func(rot,trans)
			#print(plane)
			#rospy.loginfo(plane)
		#except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
		#    pass
		except Exception as e: print(e)

		try:
			(hand_trans,hand_rot) = listener.lookupTransform('/camera_rgb_optical_frame','/marker_object_frame', rospy.Time(0))
			hand.call(hand_trans,hand_rot,hand_pose_flag)

		except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
			pass
		rate.sleep()
		
