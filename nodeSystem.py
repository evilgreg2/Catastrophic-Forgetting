import random
from PySide6.QtCore import QEasingCurve, QVariantAnimation, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QRadialGradient
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

nodes = {}
connections = {}


# Node Settings
highColor = QColor(70, 200, 110)
lowColor = QColor(220, 70, 70)
sameColor = QColor(255, 255, 255)
colorThreshold = 1
nodeCircles = {}
history = []
connectionLines = {}
connectionQueue = []
connectionAnimations = []

# Node Glow
glowAlpha = 255
glowRadius = 22
nodeGlows = {}

# Layout Settings
columnSpacing = 160
rowSpacing = 110

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


# sets the fill and keeps the glow the same color as the node
def colorNode(name, confidence):
    color = confidenceColor(confidence)
    nodeCircles[name].setBrush(color)

    x, y = nodes[name]["x"], nodes[name]["y"]
    gradient = QRadialGradient(x, y, glowRadius)
    gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), glowAlpha))
    gradient.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), glowAlpha // 2))
    gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
    nodeGlows[name].setBrush(gradient)


# Draws nodes
def drawNodes(scene):
    radius = 10
    for name, data in nodes.items():
        circle = scene.addEllipse(data["x"] - radius, data["y"] - radius, radius * 2, radius * 2, QPen(QColor(255, 255, 255), .5))
        # glow is a child so it hides and shows with the node
        glow = QGraphicsEllipseItem(data["x"] - glowRadius, data["y"] - glowRadius, glowRadius * 2, glowRadius * 2, circle)
        glow.setPen(QPen(Qt.NoPen))
        glow.setFlag(QGraphicsItem.ItemStacksBehindParent)
        nodeGlows[name] = glow
        nodeCircles[name] = circle
        colorNode(name, data["confidence"])
        circle.setVisible(data["taught"])


def loadGraph(facts, links, width, height):
    topics = []
    placed = {}
    for fact in facts:
        if fact["topic"] not in topics:
            topics.append(fact["topic"])
    lessons = max(f["lesson"] for f in facts)

    # spread the grid over the whole window, margin keeps it off the edges
    margin = 110
    columnSpacing = (width - margin * 2) / max(len(topics) - 1, 1)
    rowSpacing = (height - margin * 2) / max(lessons - 1, 1)

    for fact in facts:
        cell = (fact["topic"], fact["lesson"])
        offset = placed.get(cell, 0)
        placed[cell] = offset + 1
        x = margin + topics.index(fact["topic"]) * columnSpacing + offset * 40 + random.randint(-35, 35)
        y = margin + (fact["lesson"] - 1) * rowSpacing + offset * 40 + random.randint(-30, 30)
        nodes[fact["id"]] = {"x": x, "y": y, "confidence": 0, "taught": False}

    for pair in links:
        connections[tuple(pair)] = 0

def clearGraph():
    nodes.clear()
    connections.clear()
    history.clear()
    nodeCircles.clear()
    nodeGlows.clear()
    connectionLines.clear()
    connectionQueue.clear()
    for animation in connectionAnimations:
        animation.stop()
    connectionAnimations.clear()


# Saves a copy of all node data and all connection strengths to history
def saveHistory():
    history.append({
        "nodes": {name: dict(data) for name, data in nodes.items()},
        "connections": dict(connections),
    })



def updateNodes(newConfidence):
    for name, newValue in newConfidence.items():
        nodes[name]["confidence"] = newValue
        nodes[name]["taught"] = True

    for name, data in nodes.items():
        colorNode(name, data["confidence"])
        nodeCircles[name].setVisible(data["taught"])


# Updates connection strengths and updates each line so weaker connections are thinner and more transperant
def connectionLine(pair):
    x1, y1 = nodes[pair[0]]["x"], nodes[pair[0]]["y"]
    connectionLines[pair].setLine(x1, y1, x1, y1)
    connectionQueue.append(pair)
    if len(connectionQueue) == 1:
        drawNextLine()


def drawNextLine():
    pair = connectionQueue[0]
    line = connectionLines[pair]
    x1, y1 = nodes[pair[0]]["x"], nodes[pair[0]]["y"]
    x2, y2 = nodes[pair[1]]["x"], nodes[pair[1]]["y"]
    animation = QVariantAnimation()
    animation.setDuration(360)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.valueChanged.connect(lambda t: line.setLine(x1, y1, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    animation.finished.connect(lineFinished)
    connectionAnimations.append(animation)
    animation.start()


def lineFinished():
    if connectionQueue:
        connectionQueue.pop(0)
    if connectionQueue:
        drawNextLine()


def updateConnections(newStrengths):
    for pair, newValue in newStrengths.items():
        connections[pair] = newValue

    for pair, strength in connections.items():
        t = max(0, min(1, (strength - cutoff) / (100 - cutoff)))
        width = minWidth + (maxWidth - minWidth) * t
        alpha = int(minAlpha + (maxAlpha - minAlpha) * t)

        line = connectionLines[pair]
        if strength >= cutoff and not line.isVisible():
            connectionLine(pair)
        line.setPen(QPen(QColor(255, 255, 255, alpha), width))
        line.setVisible(strength >= cutoff)




# Shows older node and connection data by indexing saved history from the updateNodes function
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
        colorNode(name, data["confidence"])
        nodeCircles[name].setVisible(data["taught"])