'''char_generator.py'''

# -*- coding: utf-8 -*-

import cv2
import numpy as np
import preprocess
import torch
import torch.nn as nn
import torch.backends.cudnn as cudnn
from torch.autograd import Variable
from collections import OrderedDict
from scipy.ndimage import label
import config
import file
from wtd import WTD
import os
import debug
import math
import time
import postprocess
import resize

def copyStateDict(state_dict):
    if list(state_dict.keys())[0].startswith("module"):
        start_idx = 1
    else:
        start_idx = 0
    new_state_dict = OrderedDict()
    for k, v in state_dict.items():
        name = ".".join(k.split(".")[start_idx:])
        new_state_dict[name] = v
    return new_state_dict


def word_patches_cropper(img, gt, gt_len, img_path):
    cropped_img_list = list()
    for idx in range(gt_len):
        x_min, y_min, x_max, y_max = gt[idx]
        cropped_img = img[y_min:y_max, x_min:x_max]
        filename, file_ext = os.path.splitext(os.path.basename(img_path))
        cropped_file = config.jpg_cropped_images_folder_path + filename + '_' + str(idx) + '.jpg'
        cv2.imwrite(cropped_file, cropped_img)
        cropped_img_list.append(cropped_img)

    return cropped_img_list


def char_postprocess(text_map):

    text_map = text_map.copy()  # text score heatmap
    img_h, img_w = text_map.shape

    """ labeling method """
    ret, text_score = cv2.threshold(text_map, config.low_text, 1, 0)
    #debug.printing(text_score)
    nLabels, labels, stats, centroids = cv2.connectedComponentsWithStats(text_score.astype(np.uint8),
                                                                         connectivity=4)
    det = []
    mapper = []
    """Debug Global Map"""
    for k in range(1, nLabels):
        # size filtering
        size = stats[k, cv2.CC_STAT_AREA]
        if size < 10: continue

        # thresholding
        if np.max(text_map[labels == k]) < config.text_threshold: continue

        # make segmentation map
        segmap = np.zeros(text_map.shape, dtype=np.uint8)  # empty map create
        segmap[labels == k] = 255 # region of label be checked as 1
        #debug.printing(segmap)
        x, y = stats[k, cv2.CC_STAT_LEFT], stats[k, cv2.CC_STAT_TOP]
        w, h = stats[k, cv2.CC_STAT_WIDTH], stats[k, cv2.CC_STAT_HEIGHT]
        niter = int(math.sqrt(size * min(w, h) / (w * h)) * 2)
        sx, ex, sy, ey = x - niter, x + w + niter + 1, y - niter, y + h + niter + 1
        #print("stat W: {} stat H: {} niter: {}".format(w, h, niter))
        # boundary check
        if sx < 0: sx = 0
        if sy < 0: sy = 0
        if ex >= img_w: ex = img_w
        if ey >= img_h: ey = img_h

        kernel_width = int(round(w/7.0))
        kernel_height = int(round(h/3.0))
        if kernel_width is 0: kernel_width = 1
        if kernel_height is 0: kernel_height = 1

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, kernel_height))
        segmap[sy:ey, sx:ex] = cv2.dilate(segmap[sy:ey, sx:ex], kernel)
        np_contours = np.roll(np.array(np.where(segmap != 0)), 1, axis=0).transpose().reshape(-1, 2)
        rectangle = cv2.minAreaRect(np_contours)
        box = cv2.boxPoints(rectangle)
        #debug.printing(segmap)

        # align diamond-shape
        w, h = np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[1] - box[2])
        box_ratio = max(w, h) / (min(w, h) + 1e-5)
        if abs(1 - box_ratio) <= 0.1:
            l, r = min(np_contours[:, 0]), max(np_contours[:, 0])
            t, b = min(np_contours[:, 1]), max(np_contours[:, 1])
            box = np.array([[l, t], [r, t], [r, b], [l, b]], dtype=np.float32)

        # make clock-wise order
        startidx = box.sum(axis=1).argmin()
        box = np.roll(box, 4 - startidx, 0)
        box = np.array(box)

        det.append(box)
        mapper.append(k)

    return det, labels, mapper


def gen_character(generator, img, cropped_img, coord, idx, idx2):
    # prerprocess
    # RESIZE IMAGE (If image ratio is not safe, model prediction is also bad.)
    img_resized, ratio, heat_map = preprocess.resize_aspect_ratio(cropped_img, config.image_size, cv2.INTER_LINEAR, config.char_annotation_cropped_img_ratio)
    ratio_h = ratio_w = 1 / ratio

    x = preprocess.normalizeMeanVariance(img_resized)
    x = torch.from_numpy(x).permute(2, 0, 1)
    x = Variable(x.unsqueeze(0))

    '''GPU'''
    if config.cuda: x = x.cuda()

    '''predict character with pretrained model'''
    y, _ = generator(x)
    score_text = y[0, :, :, 0].cpu().data.numpy()

    '''temp area'''
    cv2.imwrite('./psd/mask/mask_' +str(idx) + '_' + str(idx2)+ '.jpg', score_text * 255)

    '''postprocess'''
    boxes, polys, _ = char_postprocess(score_text)
    box = postprocess.adjustResultCoordinates(boxes, ratio_w, ratio_h)
    for k in range(len(polys)):
        if polys[k] is None: polys[k] = boxes[k]

    box = np.array(box, dtype= np.int32)
    return_box = box[:]
    for i in range(len(box)):
        box[0] = box[0].astype(int) + coord
        cv2.polylines(img, [box[0].reshape((-1, 1, 2))], True, color=(255, 0, 0), thickness=1)
        cv2.imwrite('./psd/char_predict/tmp_' + str(idx) + '.jpg', img)
        box = box[1:]
    return return_box.tolist()

def pseudo_gt_generator():
    generator = WTD()
    print('We use pretrained model to divide cha annotation from PSD')
    print('Pretrained Path : ' + config.pretrained_model_path)
    if config.cuda:  # GPU
        generator.load_state_dict(copyStateDict(torch.load(config.pretrained_model_path)))
    else:  # ONLY CPU
        generator.load_state_dict(copyStateDict(torch.load(config.pretrained_model_path, map_location='cpu')))

    if config.cuda:
        generator = generator.cuda()
        generator = torch.nn.DataParallel(generator)
        cudnn.benchmark = False

    generator.eval()

    image_list, _, _ = file.get_files(config.jpg_images_folder_path)
    _, _, gt_list = file.get_files(config.jpg_text_ground_truth)

    if not os.path.isdir(config.jpg_cropped_images_folder_path):
        os.mkdir(config.jpg_cropped_images_folder_path)
    if not os.path.isdir(config.jpg_text_ground_truth):
        os.mkdir(config.jpg_text_ground_truth)

    datasets = {'images': image_list, 'gt': gt_list}
    char_boxes_list = list()
    for idx in range(len(datasets['images'])):
        name = preprocess.loadName(datasets['images'][idx])
        img = preprocess.loadImage(datasets['images'][idx])
        gt, length = preprocess.loadText(datasets['gt'][idx])
        resized_img, resized_gt = resize.resize_psd(img, gt, length, idx, name)
        resized_gt = np.array(resized_gt).reshape(-1,4,2)
        gt_list = resize.coord_min_and_max(resized_gt, length)
        cropped_img_list = word_patches_cropper(resized_img, gt_list, length, datasets['images'][idx])

        for k in range(length):
            char_boxes = gen_character(generator, resized_img, cropped_img_list[0], gt_list[k][:2], idx, k)
            char_boxes_list = np.append(char_boxes_list, char_boxes)
            cropped_img_list = np.delete(cropped_img_list, 0)

        char_boxes_list = char_boxes_list.reshape(-1,4,2)
        file.charSaveResult(name, char_boxes_list, dir = './psd/char_ground_truth/')
        char_boxes_list = []

