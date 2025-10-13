# Overview
This document provides a comprehensive overview of the inner workings of the AI Powered Lab Compliance Monitoring with Display Visualization System.
This system monitors laboratories to detect food or drink consumption, using an AI-driven detection pipeline integrated with an IP camera network. The objective is to automate the detection and evidence-capturing process using surveillance infrastructure and computer vision.

## **Network**
### Hardware Components
| Component                                   | Purpose                                                             |
| --------------------------------------------| ------------------------------------------------------------------- |
| **HikVision IP Cameras**                    | Capture live video feeds from different areas of labs, continuously stream footage using RTSP (Real-Time Streaming Protocol)                             |
| **DeepinMind NVR**                          | Centralized video storage and retrieval system, utilizes facial recognition capabilities to track people who violate rules at least twice                      |
| **PoE Layer 3 Switch**                      | Power over Ethernet for IP cameras                                  |
| **Router** | Connects the local network to the internet, and supports internal communication between devices      |
| **Windows 11 PC**                           | Hosts the detection pipeline and manages processing                 |
| **Display Monitor**                         | Display incompliance images, with timestamp and location            |

![Network Diagram](network-diag.drawio.png)

## **Logical Architecture**
This diagram represents the logical components of the dashboard and detection components and how they interact to detect/ display incompliances.
![Logical Architecture Diagram](logical-diag.drawio.png)

## **Detection Pipeline: Step-by-Step**
### 1. Reading Frames from Camera Stream
Each camera’s video stream is continuosly read via RTSP protocol, then the frames are submitted to the [Detection Manager](./detection/detection_manager.md).

### 2. YOLO Detction
Detection Manager dispatch the frames to [Detection Workers](./detection/detection_worker.md) using a _round robin scheduling_ approach. The Detection Workers run the YOLO object detection model inference to detect food or drinks. <br><br>
Each Detection Worker runs a YOLO object detection model to check for any visible food or drinks.

- If food or drinks are detected, the system stores:  
    - A unique track ID for each detected item (used to track objects across frames)    

    - Its bounding box information (location in the frame, class ID, confidence)  


- Next, a separate YOLO pose detection model looks for human figures in the same frame.  
    - If people are detected, it saves their landmarks (eyes, nose, ears, and wrists).    


- If at least one food/drink and one person are detected:  
    - The frame is added to the [Camera's](./camera/camera.md) processing queue.  


Regardless of detections, all frames are also sent to the dashboard display queue so they can be viewed in the live video feed.

### 3. Matching People to Food/Drinks
The `association()` function continuously attempts to associate the most likely owner of each food/ drink present in the frame by calculating how close each person’s nose and wrists are to the food/drink bounding box using the Euclidean distance between:  

  - the nose and wrist landmarks  
  
  - the bounding box of the food/ drink  

The closest person is assumed to be the owner.  

To avoid false alarms like someone walking by, the system waits until the person has maintained close wrist proximity for at least 2 seconds before counting it as an incompliance.  

### 4. Saving Incompliance Snapshots
When an incompliance is confirmed:  
The face area is cropped and sent to the [NVR](./incompliance/nvr.md) for facial recognition.  

- If a **match is found** on a **different date**:
    - This means that the person has at least 1 previous incompliance

    - The incompliance is logged, incompliance details for person updated in datasbase

    - The face crop is saved in the NVR's face database (under the name "Incompliance") for future use

    - Frame pushed to queue in [Saver](./incompliance/saver.md) and saved in web/static/incompliances/

- If a **match is found** on the **same date**:
    - The system will disregard it

    - This is to prevent the same individual from being detected repeatedly within consecutive frames on the same day, ensuring that only new or distinct incompliances are logged  

- If **no match** is found:
    - The system will treat the individual as a new person committing the incompliance 

    - The incompliance is logged, new person created in the database

    - The face crop is saved in the NVR's face database (under the name "Incompliance") for future use

    - Frame pushed to queue in Saver and saved in web/static/incompliances/ 

## **Detection Pipeline Flowchart**
![Detection Flowchart](detection-flowchart.drawio.png)
