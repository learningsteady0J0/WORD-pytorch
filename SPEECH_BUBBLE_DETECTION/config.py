import numpy as np

RNG_SEED = 3

#TEST PATH
TEST_IMAGE_PATH = './test/images/'
TEST_PREDICTION_PATH = './test/predictions/'

#TEST HYPERPARAMETER
TEST_SCALES = (600,)
TEST_MAX_SIZE = 1000
PIXEL_MEANS = np.array([[[102.9801, 115.9465, 122.7717]]])
TEST_BBOX_REG = True
TEST_NMS = 0.3
POOLING_MODE = 'crop'

#TRAIN HYPERPARAMETER
TRAIN_BBOX_NORMALIZE_MEANS = (0.0, 0.0, 0.0, 0.0)
TRAIN_BBOX_NORMALIZE_STDS = (0.1, 0.1, 0.2, 0.2)
TRAIN_BBOX_NORMALIZE_TARGETS_PRECOMPUTED = True

#BBOX THRESHOLD
THRESH = 0.05

#BACKBONE NETWORK
BACKBONE = 'res101'

#CUDA
cuda = True

#MODEL PATH
PRETRAINED_MODEL_PATH = './pretrained_models/Speech-Bubble-Detector.pth'