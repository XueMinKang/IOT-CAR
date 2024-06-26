######## Picamera Object Detection Using Tensorflow Classifier #########
#
# Author: Evan Juras
# Date: 4/15/18
# Description: 
# This program uses a TensorFlow classifier to perform object detection.
# It loads the classifier uses it to perform object detection on a Picamera feed.
# It draws boxes and scores around the objects of interest in each frame from
# the Picamera. It also can be used with a webcam by adding "--usbcam"
# when executing this script from the terminal.

## Some of the code is copied from Google's example at
## https://github.com/tensorflow/models/blob/master/research/object_detection/object_detection_tutorial.ipynb

## and some is copied from Dat Tran's example at
## https://github.com/datitran/object_detector_app/blob/master/object_detection_app.py

## but I changed it to make it more understandable to me.


# Import packages
import os
import cv2
import numpy as np
from picamera.array import PiRGBArray
from picamera import PiCamera
import tensorflow as tf
import argparse
import sys
import pwm_motor as motor
import time
import RPi.GPIO as GPIO
import readchar
from gtts import gTTS



BUZZ_PIN = 29
LED_PIN = 31
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUZZ_PIN, GPIO.OUT)
pwmled = GPIO.PWM(LED_PIN,100)
pwm = GPIO.PWM(BUZZ_PIN, 262)
pwm.start(0)
pwmled.start(0)
pwmled.ChangeDutyCycle(0)
pwm.ChangeFrequency(262)
pwm.ChangeDutyCycle(0)
# Set up camera constants
#IM_WIDTH = 1280
#IM_HEIGHT = 720
IM_WIDTH = 640
# Use smaller resolution for
IM_HEIGHT = 480
counter = 0
# slightly faster framerate

# Select camera type (if user enters --usbcam when calling this script,
# a USB webcam will be used)
camera_type = 'usb'
parser = argparse.ArgumentParser()
parser.add_argument('--usbcam', help='Use a USB webcam instead of picamera',
                    action='store_true')
parser.add_argument('--picam', help='Use a picamera',
                    action='store_true')
args = parser.parse_args()
if args.usbcam:
	camera_type = 'usb'
if args.picam:
	camera_type = 'picamera'

# This is needed since the working directory is the object_detection folder.
sys.path.append('..')

# Import utilites
from utils import label_map_util
from utils import visualization_utils as vis_util

# Name of the directory containing the object detection module we're using
MODEL_NAME = 'ssdlite_mobilenet_v2_coco_2018_05_09'

# Grab path to current working directory
CWD_PATH = os.getcwd()

# Path to frozen detection graph .pb file, which contains the model that is used
# for object detection.
PATH_TO_CKPT = os.path.join(CWD_PATH,MODEL_NAME,'frozen_inference_graph.pb')

# Path to label map file
PATH_TO_LABELS = os.path.join(CWD_PATH,'data','mscoco_label_map.pbtxt')

# Number of classes the object detector can identify
NUM_CLASSES = 90

## Load the label map.
# Label maps map indices to category names, so that when the convolution
# network predicts `5`, we know that this corresponds to `airplane`.
# Here we use internal utility functions, but anything that returns a
# dictionary mapping integers to appropriate string labels would be fine
label_map = label_map_util.load_labelmap(PATH_TO_LABELS)
categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=NUM_CLASSES, use_display_name=True)
category_index = label_map_util.create_category_index(categories)

# Load the Tensorflow model into memory.
detection_graph = tf.Graph()
with detection_graph.as_default():
	od_graph_def = tf.GraphDef()
	with tf.gfile.GFile(PATH_TO_CKPT, 'rb') as fid:
		serialized_graph = fid.read()
		od_graph_def.ParseFromString(serialized_graph)
		tf.import_graph_def(od_graph_def, name='')

	sess = tf.Session(graph=detection_graph)


# Define input and output tensors (i.e. data) for the object detection classifier

# Input tensor is the image
image_tensor = detection_graph.get_tensor_by_name('image_tensor:0')

# Output tensors are the detection boxes, scores, and classes
# Each box represents a part of the image where a particular object was detected
detection_boxes = detection_graph.get_tensor_by_name('detection_boxes:0')

# Each score represents level of confidence for each of the objects.
# The score is shown on the result image, together with the class label.
detection_scores = detection_graph.get_tensor_by_name('detection_scores:0')
detection_classes = detection_graph.get_tensor_by_name('detection_classes:0')

# Number of objects detected
num_detections = detection_graph.get_tensor_by_name('num_detections:0')

# Initialize frame rate calculation
frame_rate_calc = 1
freq = cv2.getTickFrequency()
font = cv2.FONT_HERSHEY_SIMPLEX

def CheckDirection(arg_boxes,arg_pwm,arg_pwmled):
	alldirection = {"Left":True,"Right":True,"Forward":True,"Backward":True,"isControlMode":False}
	objx = arg_boxes[3] - arg_boxes[1]
	objy = arg_boxes[2] - arg_boxes[0]
	screenleftx = 0.33
	screenrightx = 0.66
	#object too close or too big
	if arg_boxes[3] > screenrightx and arg_boxes[1] < screenleftx:
		alldirection["Right"] = False
		alldirection["Forward"] = False
		alldirection["Left"] = False
	#object in the right
	if arg_boxes[3] > screenrightx:
		alldirection["Right"] = False
	#object in the middle
	if screenleftx < arg_boxes[3] < screenrightx:
		alldirection["Forward"] = False
	#object in the left
	if arg_boxes[3] < screenleftx:
		alldirection["Left"] = False
	#object in the right
	if arg_boxes[1] > screenrightx:
		alldirection["Right"] = False
	#object in the middle
	if screenleftx < arg_boxes[1] < screenrightx:
		alldirection["Forward"] = False
	#object in the left
	if arg_boxes[1] < screenleftx:
		alldirection["Left"] = False

	if objx > 0.7 or objy > 0.7:
		arg_pwm.ChangeDutyCycle(50)
		arg_pwmled.ChangeDutyCycle(100)
		alldirection["Right"] = False
		alldirection["Forward"] = False
		alldirection["Left"] = False
		alldirection["isControlMode"] = True
		time.sleep(1)
		arg_pwm.ChangeDutyCycle(0)
		arg_pwmled.ChangeDutyCycle(0)
		os.system('omxplayer -o local -p switch.mp3 > /dev/null 3>&1')
	return alldirection

def Control_Mode():
	iscontrolmode = True
	ch = readchar.readkey()
	if ch == 'w':
		motor.forward()
	elif ch == 's':
		motor.backward()
	elif ch == 'd':
		motor.turnRight()
	elif ch == 'a':
		motor.turnLeft()
	elif ch == 'q':
		iscontrolmode = False
		os.system('omxplayer -o local -p switch.mp3 > /dev/null 3>&1')
	return iscontrolmode

def Auto_Mode(arg_num,arg_cs,arg_sc,arg_boxes,arg_frame,arg_pwm,arg_pwmled):
	global  counter
	mAllDirection = {"Left": True, "Right": True, "Forward": True, "Backward": True, "isControlMode": False}
	for i in range(int(arg_num[0])):
		if arg_cs[i] == 1 and arg_sc[i] > 0.5:
			mAllDirection = CheckDirection(arg_boxes[0][i],arg_pwm,arg_pwmled)
		# break
	if counter > 0: #right>left
		if mAllDirection["Forward"]:
			motor.forward()
		elif mAllDirection["Left"]:
			motor.turnLeft()
			counter-=1
		elif mAllDirection["Right"]:
			motor.turnRight()
			counter+=1
		else:
			motor.backward()
	elif counter <= 0:
		if mAllDirection["Forward"]:
			motor.forward()
		elif mAllDirection["Right"]:
			motor.turnRight()
			counter+=1
		elif mAllDirection["Left"]:
			motor.turnLeft()
			counter-=1
		else:
			motor.backward()

	return mAllDirection["isControlMode"]


# Initialize camera and perform object detection.
# The camera has to be set up and used differently depending on if it's a
# Picamera or USB webcam.

# I know this is ugly, but I basically copy+pasted the code for the object
# detection loop twice, and made one work for Picamera and the other work
# for USB.

### Picamera ###
if camera_type == 'picamera':

	# Initialize Picamera and grab reference to the raw capture
	camera = PiCamera()
	# camera.vflip = True
	# camera.hflip = True
	camera.resolution = (IM_WIDTH,IM_HEIGHT)
	camera.framerate = 10
	rawCapture = PiRGBArray(camera, size=(IM_WIDTH,IM_HEIGHT))
	rawCapture.truncate(0)

	for frame1 in camera.capture_continuous(rawCapture, format="bgr",use_video_port=True):

		t1 = cv2.getTickCount()

		# Acquire frame and expand frame dimensions to have shape: [1, None, None, 3]
		# i.e. a single-column array, where each item in the column has the pixel RGB value
		frame = np.copy(frame1.array)
		frame.setflags(write=1)
		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
		frame_expanded = np.expand_dims(frame_rgb, axis=0)

		# Perform the actual detection by running the model with the image as input
		(boxes, scores, classes, num) = sess.run(
			[detection_boxes, detection_scores, detection_classes, num_detections],
			feed_dict={image_tensor: frame_expanded})

		# Draw the results of the detection (aka 'visulaize the results')
		vis_util.visualize_boxes_and_labels_on_image_array(
			frame,
			np.squeeze(boxes),
			np.squeeze(classes).astype(np.int32),
			np.squeeze(scores),
			category_index,
			use_normalized_coordinates=True,
			line_thickness=3,
			min_score_thresh=0.01)

		cv2.putText(frame,"FPS: {0:.2f}".format(frame_rate_calc),(30,50),font,1,(255,255,0),2,cv2.LINE_AA)

		# All the results have been drawn on the frame, so it's time to display it.
		cv2.imshow('Object detector', frame)

		t2 = cv2.getTickCount()
		time1 = (t2-t1)/freq
		frame_rate_calc = 1/time1

		# Press 'q' to quit
		if cv2.waitKey(1) == ord('q'):
			break

		rawCapture.truncate(0)

### USB webcam ###
elif camera_type == 'usb':
	# Initialize USB webcam feed
	camera = cv2.VideoCapture(0, cv2.CAP_V4L)
	ret = camera.set(3,IM_WIDTH)
	ret = camera.set(4,IM_HEIGHT)
	isControlMode = False
	while True:
		# t1 = cv2.getTickCount()
        # Acquire frame and expand frame dimensions to have shape: [1, None, None, 3]
		# i.e. a single-column array, where each item in the column has the pixel RGB value
		ret, frame = camera.read()
		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
		frame_expanded = np.expand_dims(frame_rgb, axis=0)

		# Perform the actual detection by running the model with the image as input
		(boxes, scores, classes, num) = sess.run(
			[detection_boxes, detection_scores, detection_classes, num_detections],
			feed_dict={image_tensor: frame_expanded})

		# Draw the results of the detection (aka 'visulaize the results'
		vis_util.visualize_boxes_and_labels_on_image_array(
			frame,
			np.squeeze(boxes),
			np.squeeze(classes).astype(np.int32),
			np.squeeze(scores),
			category_index,
			use_normalized_coordinates=True,
			line_thickness=3,
			min_score_thresh=0.01)
		# print(boxes[0][:10])
		# print(np.squeeze(classes))
		# print(np.squeeze(scores))
		# print(category_index)
		cs = np.squeeze(classes).astype(np.int32)
		sc = np.squeeze(scores)
		if isControlMode:
			print("Control Mode\n")
			isControlMode = Control_Mode()

		else:
			print("Auto Mode\n")
			isControlMode = Auto_Mode(num, cs, sc, boxes, frame,pwm,pwmled)
		#time.sleep(1)
		cv2.line(frame,(213,0),(213,480),(0,0,255),5)
		cv2.line(frame, (426, 0), (426, 480), (0, 0, 255), 5)
		cv2.imshow('Object detector', frame)


		if cv2.waitKey(1) == ord('q'):
			break
		# cv2.putText(frame,"FPS: {0:.2f}".format(frame_rate_calc),(30,50),font,1,(255,255,0),2,cv2.LINE_AA)

        # All the results have been drawn on the frame, so it's time to display it.

		# t2 = cv2.getTickCount()
        # time1 = (t2-t1)/freq
        # frame_rate_calc = 1/time1

        # Press 'q' to quit

motor.cleanup()
camera.release()
cv2.destroyAllWindows()
pwm.stop()
pwmled.stop()
GPIO.cleanup()





