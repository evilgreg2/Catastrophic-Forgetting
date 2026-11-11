from PySide6.QtGui import QPainter, QPen, QColor


nodes = {
    "Node_A": {"x": 100, "y": 150, "confidence": 45},
    "Node_B": {"x": 300, "y": 100, "confidence": 85},
    "Node_C": {"x": 500, "y": 200, "confidence": 0},
    "Node_D": {"x": 200, "y": 350, "confidence": 50},
}

connections = {
    ("Node_A", "Node_B"): 80,
    ("Node_B", "Node_C"): 55,
    ("Node_A", "Node_D"): 20,
}

neighbors = {name: [] for name in nodes}
for a, b in connections.keys():
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
connectionLines = {}

# Connection Settings
cutoff = 10
minWidth = 1
maxWidth = 4
minAlpha = 50
maxAlpha = 255


def connectNodes(scene, nodeA, nodeB):
    nodeAX, nodeAY = nodes[nodeA]["x"], nodes[nodeA]["y"]
    nodeBX, nodeBY = nodes[nodeB]["x"], nodes[nodeB]["y"]

    strength = connections[(nodeA, nodeB)]

    t = max(0, min(1, (strength - cutoff) / (100 - cutoff)))

    width = minWidth + (maxWidth - minWidth) * t
    alpha = int(minAlpha + (maxAlpha - minAlpha) * t)

    line = scene.addLine(nodeAX, nodeAY, nodeBX, nodeBY, QPen(QColor(255, 255, 255, alpha), width))
    line.setZValue(-1)
    line.setVisible(strength >= cutoff)
    connectionLines[(nodeA, nodeB)] = line



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


# Saves a copy of all node data and all connection strengths to history
def saveHistory():
    history.append({
        "nodes": {name: dict(data) for name, data in nodes.items()},
        "connections": dict(connections),
    })



def updateNodes(newConfidence):
    previousData = history[-1]["nodes"]

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


# Updates connection strengths and updates each line so weaker connections are thinner and more transperant
# Takes
#    newStrengths a dictionary of node pair to its new strength
def updateConnections(newStrengths):
    for pair, newValue in newStrengths.items():
        connections[pair] = newValue

    for pair, strength in connections.items():
        t = max(0, min(1, (strength - cutoff) / (100 - cutoff)))
        width = minWidth + (maxWidth - minWidth) * t
        alpha = int(minAlpha + (maxAlpha - minAlpha) * t)

        line = connectionLines[pair]
        line.setPen(QPen(QColor(255, 255, 255, alpha), width))
        line.setVisible(strength >= cutoff)




# Shows older node and connection data by indexing saved history from the updateNodes function
# sliderValue - Not defined yet
sliderValue = 0
def readHistory(sliderValue):
    if not history:
        return
    sliderValue = max(0, min(sliderValue, len(history) - 1))
    snapshot = history[sliderValue]["nodes"]
    savedStrengths = history[sliderValue]["connections"]


    for pair, strength in savedStrengths.items():
        t = max(0, min(1, (strength - cutoff) / (100 - cutoff)))
        width = minWidth + (maxWidth - minWidth) * t
        alpha = int(minAlpha + (maxAlpha - minAlpha) * t)

        line = connectionLines[pair]
        line.setPen(QPen(QColor(255, 255, 255, alpha), width))
        line.setVisible(strength >= cutoff)    

    for name, data in snapshot.items():
        if sliderValue == 0:
            difference = 0
        else:
            difference = data["confidence"] - history[sliderValue - 1]["nodes"][name]["confidence"]

        nodeCircles[name].setBrush(confidenceColor(data["confidence"]))
        if difference >= colorThreshold:
            nodeCircles[name].setPen(QPen(highColor, 3))
        elif difference <= -colorThreshold:
            nodeCircles[name].setPen(QPen(lowColor, 3))
        else:
            nodeCircles[name].setPen(QPen(sameColor, 3))
