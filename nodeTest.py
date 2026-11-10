from math import sqrt
from PySide6.QtGui import QPainter, QPen, QColor


nodes = {
    "Node_A": {"x": 100, "y": 150, "confidence": 45},
    "Node_B": {"x": 300, "y": 100, "confidence": 85},
    "Node_C": {"x": 500, "y": 200, "confidence": 0},
    "Node_D": {"x": 200, "y": 350, "confidence": 50},
}

connections = [
    ("Node_A", "Node_B"),
    ("Node_B", "Node_C"),
    ("Node_A", "Node_D")
        ]

neighbors = {name: [] for name in nodes}
for a, b in connections:
    neighbors[a].append(b)
    neighbors[b].append(a)


for name, data in nodes.items():
    x = data["x"]
    y = data["y"]
    confidence = data["confidence"]
    linked_to = neighbors[name]
    print(name, x, y, confidence, linked_to)

# Node Settings
highColor = QColor(70, 200, 110)
lowColor = QColor(220, 70, 70)
sameColor = QColor(255, 255, 255)
colorThreshold = 1
nodeCircles = {}
history = []


def connectNodes(scene, nodeA, nodeB):
    nodeAX, nodeAY =  nodes[nodeA]["x"], nodes[nodeA]["y"]
    nodeBX, nodeBY =  nodes[nodeB]["x"], nodes[nodeB]["y"]

    # Calculate the distance between nodes using the distance formula
    distance = sqrt(abs((nodeBX - nodeAX)**2 + (nodeBY - nodeAY)**2))

    # Creates a line if the distance between nodes is equal to or less than 150
    if distance <=  150:
        scene.addLine(nodeAX, nodeAY, nodeBX, nodeBY, QPen(QColor(255, 255, 255), 2))



def confidenceColor(confidence):
    t = max(0, min(confidence, 100)) / 100
    hue = int(t * 120)
    return QColor.fromHsv(hue, 200, 220)

# Draws nodes
def drawNodes(scene):
    radius = 10
    for name, data in nodes.items():
        circle = scene.addEllipse(data["x"] - radius, data["y"] - radius, radius * 2, radius * 2, QPen(QColor(255, 255, 255), 2))
        circle.setBrush(confidenceColor(data["confidence"]))
        nodeCircles[name] = circle


# Saves all node data and updates node colors according to changes in confidence
def updateNodes(newConfidence):
    if not history:
        history.append({name: dict(data) for name, data in nodes.items()})
    previousData = history[-1]

    for name, newValue in newConfidence.items():
        nodes[name]["confidence"] = newValue

    for name, data in nodes.items():
        nodeCircles[name].setBrush(confidenceColor(data["confidence"]))
        difference = data["confidence"] - previousData[name]["confidence"]
        if difference >= colorThreshold:
            nodeCircles[name].setPen(QPen(highColor, 3))
        elif difference <= -colorThreshold:
            nodeCircles[name].setPen(QPen(lowColor, 3))
        else:
            nodeCircles[name].setPen(QPen(sameColor, 3))


    history.append({name: dict(data) for name, data in nodes.items()})


# Shows older node data by indexing saved history from the updateNodes function
# sliderValue - Not defined yet

sliderValue = 0
def readHistory(sliderValue):
    if not history:
        return
    sliderValue = max(0, min(sliderValue, len(history) - 1))
    snapshot = history[sliderValue]

    for name, data in snapshot.items():
        if sliderValue == 0:
            difference = 0
        else:
            difference = data["confidence"] - history[sliderValue - 1][name]["confidence"]

        nodeCircles[name].setBrush(confidenceColor(data["confidence"]))
        if difference >= colorThreshold:
            nodeCircles[name].setPen(QPen(highColor, 3))
        elif difference <= -colorThreshold:
            nodeCircles[name].setPen(QPen(lowColor, 3))
        else:
            nodeCircles[name].setPen(QPen(sameColor, 3))
