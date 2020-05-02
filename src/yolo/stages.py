# USAGE
# python yolo.py --image images/baggage_claim.jpg --yolo yolo-coco

# import the necessary packages
import numpy as np
import argparse
import time
import cv2
import os
import glob


DEBUG = False

def main():
    import configparser
    config = configparser.ConfigParser()
    config.read("config.py") 

    prefix = config["DEFAULT"]["prefix"]
    image_dir = prefix+config["YOLO"]["input_image_dir"]
    print(image_dir)
    detector_path = prefix+config["YOLO"]["darknet_model_dir"]
    confidence = float(config["YOLO"]["confidence"])
    threshold = float(config["YOLO"]["threshold"])
    pipeline(image_dir, detector_path, confidence, threshold)

def pipeline(image_dir, detector_path, confidence, threshold):
    (vd_net, vd_labels) = setup_detector(detector_path, "vehicle-detection")
    (lpd_net, lpd_labels) = setup_detector(detector_path, "lp-detection-layout-classification")
    (lpr_net, lpr_labels) = setup_detector(detector_path, "lp-recognition")

    images = [f for f in glob.glob(image_dir + "/*.jpg")]
    for img in images:
        print(img)
        # load our input image and grab its spatial dimensions
        image = cv2.imread(img)
        if empty_image(image):
            continue
        image_name = os.path.splitext(os.path.basename(img))[0]
        (boxes, confidences, classIDs, vehicles) = run_object_detector(image, vd_net, vd_labels, confidence, threshold, image_name)
        #cv2.imshow("Image", image)
        #cv2.waitKey(0)

        for (vehicle, v_name) in vehicles:
             if empty_image(vehicle):
                 continue
             (boxes, confidences, classIDs, lps) = run_object_detector(vehicle, lpd_net, lpd_labels, confidence, threshold, v_name)
             #cv2.imshow("vehicle", vehicle)
             #cv2.waitKey(0)

             for (lp, lp_name) in lps:
                if empty_image(lp):
                    continue
                (boxes, confidences, classIDs, plate_contents) = run_object_detector(lp, lpr_net, lpr_labels, confidence, threshold, lp_name)
                count = 0
                for i in classIDs:
                    #import pdb; pdb.set_trace()
                    text = "{}: {:.4f}".format(lpr_labels[i], confidences[count])
                    print(text)
                    count = count+1
                #cv2.imshow("plate", lp)
                cv2.imwrite("plate"+lp_name+".jpg", lp)
                #cv2.waitKey(0)

def empty_image(image):
    (H, W) = image.shape[:2]
    if W<=0 or H<=0:
        print("W or H <=0")
        return True
    return False



def setup_detector(detector_path, detector_name):
    # load the COCO class labels our YOLO model was trained on
    labelsPath = os.path.sep.join([detector_path, detector_name+".names"])
    labels = open(labelsPath).read().strip().split("\n")

    # derive the paths to the YOLO weights and model configuration
    weightsPath = os.path.sep.join([detector_path, detector_name+".weights"])
    configPath = os.path.sep.join([detector_path, detector_name+".cfg"])

    # load our YOLO object detector trained on COCO dataset (80 classes)
    print("[INFO] loading YOLO from disk...")
    net = cv2.dnn.readNetFromDarknet(configPath, weightsPath)
    
    return (net, labels)

def run_object_detector(image, net, labels, min_confidence, threshold, image_name):
    (H, W) = image.shape[:2]
    if W<=0 or H<=0:
        print("W or H <=0")

    # determine only the *output* layer names that we need from YOLO
    ln = net.getLayerNames()
    ln = [ln[i[0] - 1] for i in net.getUnconnectedOutLayers()]


    # construct a blob from the input image and then perform a forward
    # pass of the YOLO object detector, giving us our bounding boxes and
    # associated probabilities
    
    #cv2.imshow("original_img", image)
    #cv2.waitKey(0)
    #blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (416, 416),
    blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (448, 288),
            swapRB=True, crop=False)
    net.setInput(blob)
    start = time.time()
    layerOutputs = net.forward(ln)
    end = time.time()

    # initialize a list of colors to represent each possible class label
    np.random.seed(42)
    COLORS = np.random.randint(0, 255, size=(len(labels), 3),
	dtype="uint8")
    

    # show timing information on YOLO
    print("[INFO] YOLO took {:.6f} seconds".format(end - start))

    # initialize our lists of detected bounding boxes, confidences, and
    # class IDs, respectively
    boxes = []
    confidences = []
    classIDs = []

    # loop over each of the layer outputs
    for output in layerOutputs:
            # loop over each of the detections
            for detection in output:
                    # extract the class ID and confidence (i.e., probability) of
                    # the current object detection
                    scores = detection[5:]
                    classID = np.argmax(scores)
                    confidence = scores[classID]

                    # filter out weak predictions by ensuring the detected
                    # probability is greater than the minimum probability
                    #import pdb; pdb.set_trace()
                    if confidence > min_confidence:
                            # scale the bounding box coordinates back relative to the
                            # size of the image, keeping in mind that YOLO actually
                            # returns the center (x, y)-coordinates of the bounding
                            # box followed by the boxes' width and height
                            box = detection[0:4] * np.array([W, H, W, H])
                            (centerX, centerY, width, height) = box.astype("int")

                            # use the center (x, y)-coordinates to derive the top and
                            # and left corner of the bounding box
                            x = int(centerX - (width / 2))
                            y = int(centerY - (height / 2))

                            # update our list of bounding box coordinates, confidences,
                            # and class IDs
                            boxes.append([x, y, int(width), int(height)])
                            confidences.append(float(confidence))
                            classIDs.append(classID)

    # apply non-maxima suppression to suppress weak, overlapping bounding
    # boxes
    idxs = cv2.dnn.NMSBoxes(boxes, confidences, min_confidence,
            threshold)

    cropped_images = []

    # ensure at least one detection exists
    if len(idxs) > 0:
            # loop over the indexes we are keeping
            for i in idxs.flatten():
                    # extract the bounding box coordinates
                    (x, y) = (boxes[i][0], boxes[i][1])
                    (w, h) = (boxes[i][2], boxes[i][3])

                    # draw a bounding box rectangle and label on the image
                    color = [int(c) for c in COLORS[classIDs[i]]]
                    cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
                    text = "{}: {:.4f}".format(labels[classIDs[i]], confidences[i])
                    cv2.putText(image, text, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, color, 2)
                    vname = image_name + "_" + str(i) + "_" + str(classIDs[i]) + "_" + str(confidences[i])
                    cropped = image[y:y+h, x:x+w]
                    
                    if DEBUG:
                        #cv2.imshow("original_img", image)
                        #cv2.waitKey(0)
                        filename = vname + ".jpg"
                        #cv2.imshow(vname, cropped)
                        #cv2.waitKey(0)
                        cv2.imwrite(filename, cropped)

                    cropped_images.append((cropped, vname))

    # show the output image
    return (boxes, confidences, classIDs, cropped_images)

if __name__ == "__main__":
    main()
