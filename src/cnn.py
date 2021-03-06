#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Sat Apr  7 20:13:18 2018

@author: caoxiya
"""
import tensorflow as tsf
import numpy as np
import cv2 

#Training = True
BUFFER = 0
VALID = 800

class DataLoader(object):
    
    def __init__(self, path, shape_x, shape_y, validation_size, batch_size):
        self.path = path
        self.x = shape_x #width of the image
        self.y = shape_y #height of the image
        self.vsz = validation_size
        self.bsz = batch_size #batch_size % 3 should be zero
        if Training:
            self.buffer = BUFFER
        else:
            self.buffer = VALID
        
    def readClass(self, cn, num):
        #cn is classname
        images = []
        for i in range(self.buffer, self.buffer + self.bsz / 3):
            #self.path = '/Users/caoxiya/Desktop/data/'
            img = cv2.imread(self.path + cn + '/' + cn + '_' + str(i) + '.png')
            img = cv2.resize(img, (self.x, self.y), interpolation = cv2.INTER_AREA)
            #print self.path + cn + '/' + cn + '_' + str(i) + '.png'
            img = np.reshape(img, self.x * self.y * 3)
            images.append(img)#the size of image is y * x * 3
        images = np.array(images)
        labels = num * np.ones(len(images))
        return images, labels
    
    def nextBatch(self):
        image0, label0 = self.readClass('up', 0)
        image1, label1 = self.readClass('mid', 1)
        image2, label2 = self.readClass('down', 2)
        x = np.concatenate((image0, image1), axis=0)
        x = np.concatenate((x, image2), axis=0)
        y = np.concatenate((label0, label1), axis=0)
        y = np.concatenate((y, label2), axis=0)
        self.buffer = (self.buffer + self.bsz) % VALID
        y = y.astype(int)
        return x, y
    
    
class CNNModel(object):
    
    def __init__(self, shape_x, shape_y, sess, optimizer):
        
        self.x = shape_x
        self.y = shape_y
        with tsf.name_scope('input'):
            inputImages = tsf.placeholder(tsf.float32,[None, shape_x * shape_y * 3])
            
        with tsf.name_scope('labels'):
            imagelabels = tsf.placeholder(tsf.int32, [None])
            
        ylabels = tsf.one_hot(imagelabels, 2)
        with tsf.name_scope('reshape'):
            x_image = tsf.reshape(inputImages,[-1, shape_y, shape_x, 3])
        # First convolutional layer - maps 3 channels image to 32 feature maps.
        with tsf.name_scope('conv1'):
            W_conv1 = self.weight_variable([5, 5, 3, 32])
            b_conv1 = self.bias_variable([32])
            h_conv1 = tsf.nn.relu(self.conv2d(x_image, W_conv1) + b_conv1)
        # Pooling layer - downsamples by 2X.
        with tsf.name_scope('pool1'):
            h_pool1 = self.max_pool_2x2(h_conv1)
            
        # Second convolutional layer -- maps 32 feature maps to 64.
        with tsf.name_scope('conv2'):
            W_conv2 = self.weight_variable([5, 5, 32, 64])
            b_conv2 = self.bias_variable([64])
            h_conv2 = tsf.nn.relu(self.conv2d(h_pool1, W_conv2) + b_conv2)            
        # Second pooling layer.
        with tsf.name_scope('pool2'):
            h_pool2 = self.max_pool_2x2(h_conv2)
            
        # Fully connected layer 1 -- after 2 round of downsampling, our 28x28 image
        # is down to 7x7x64 feature maps -- maps this to 1024 features.
        with tsf.name_scope('fc1'):
            W_fc1 = self.weight_variable([self.x * self.y * 64 / 16, 1024])
            b_fc1 = self.bias_variable([1024])
            h_pool2_flat = tsf.reshape(h_pool2, [-1, self.x * self.y * 64 / 16])
            h_fc1 = tsf.nn.relu(tsf.matmul(h_pool2_flat, W_fc1) + b_fc1)
        # Dropout - controls the complexity of the model, prevents co-adaptation of features.
        with tsf.name_scope('dropout'):
            keep_prob = tsf.placeholder(tsf.float32)
            h_fc1_drop = tsf.nn.dropout(h_fc1, keep_prob)
        
        # Map the 1024 features to 10 classes, one for each digit
        with tsf.name_scope('fc2'):
            W_fc2 = self.weight_variable([1024, 2])
            b_fc2 = self.bias_variable([2])
            y_conv = tsf.matmul(h_fc1_drop, W_fc2) + b_fc2
  
        with tsf.name_scope('loss'):
            cross_entropy = tsf.nn.softmax_cross_entropy_with_logits_v2(labels=ylabels, logits=y_conv)
            
        cross_entropy = tsf.reduce_mean(cross_entropy)
        with tsf.name_scope('accuracy'):
            accuracy = tsf.reduce_mean(tsf.cast(tsf.equal(tsf.argmax(y_conv, 1), tsf.argmax(ylabels, 1)), tsf.float32))
            
        with tsf.name_scope('output'):
            output = tsf.argmax(y_conv, 1)
        tsf.add_to_collection("output", output)
        
        self.train_op = optimizer.minimize(cross_entropy)
        self.input = inputImages
        self.labels = imagelabels
        self.output = output
        self.loss = cross_entropy
        self.optimizer = optimizer
        self.keep_prob = keep_prob
        self.accuracy = accuracy
        self.sess = sess
    
        
    def Predict(self, inputImages, kp):
        return self.sess.run(self.output, feed_dict={self.input:inputImages, self.keep_prob:kp})
    
    def Train(self, inputImages, imagelabels, kp):
        return self.sess.run([self.loss, self.train_op], feed_dict={self.input:inputImages, self.labels:imagelabels, self.keep_prob:kp})
        
    def weight_variable(self, shape):
        """weight_variable generates a weight variable of a given shape."""
        initial = tsf.truncated_normal(shape, stddev=0.1)
        return tsf.Variable(initial)
    
    def conv2d(self, x, W):
        """conv2d returns a 2d convolution layer with full stride."""
        return tsf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='SAME')
    
    
    def max_pool_2x2(self,x):
        """max_pool_2x2 downsamples a feature map by 2X."""
        return tsf.nn.max_pool(x, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')
    
    def bias_variable(self, shape):
        """bias_variable generates a bias variable of a given shape."""
        initial = tsf.constant(0.1, shape=shape)
        return tsf.Variable(initial)


def restoreModel(sess, saver, modelName):
    print("Restoring model")
    saver.restore(sess, modelName)
    
    
def classify(Training,imageInput):  
	path = '/home/tommy/catkin_ws/src/compute_tf/src/'
	shape_x = 80
	shape_y = 180
	lr = 1e-3
	if Training:
		episode = 180
		validation_size = 0
		batch_size = 15
		dataset = DataLoader(path, shape_x, shape_y, validation_size, batch_size)
		sess = tsf.Session()
		optimizer = tsf.train.AdamOptimizer(lr)
		model = CNNModel(shape_x, shape_y, sess, optimizer)
		sess.run(tsf.global_variables_initializer())
		saver = tsf.train.Saver()
		for epi in range(episode):
		    imageInput, imagelabels = dataset.nextBatch()
		    #print type(imagelabels)
		    loss, _ = model.Train(imageInput, imagelabels, 0.5)
		    print loss
		    
		save_path = saver.save(sess, path + "model/model.ckpt")
		print "Model saved in path: %s" % save_path
	else:
		'''
		tsf.reset_default_graph()
		sess = tsf.Session()
	
		#restoreModel(sess, saver1, path + "model/model.ckpt")
		optimizer = tsf.train.AdamOptimizer(lr)
		model = CNNModel(shape_x, shape_y, sess, optimizer)
		saver1 = tsf.train.Saver()
		restoreModel(sess, saver1, path + "model/model.ckpt")
		'''
		predict = model.Predict(imageInput,0.5)
		
		#sess.close()
	
		return predict
		'''
		for test in range(200):
		    dataset = DataLoader(path, shape_x, shape_y, 0, 3)
		    imageInput, imagelabels = dataset.nextBatch()
		    predict = model.Predict(imageInput,0.5)
		    print predict
		'''

