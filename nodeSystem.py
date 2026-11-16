import math
import random
from PySide6.QtCore import QEasingCurve, QVariantAnimation, QTimer, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QRadialGradient
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

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
shownConfidence = {}
nodeFades = {}
selected = None
factInfo = {}
infoBox = None
targetConfidence = {}

# Float Settings
floatSize = 4
floatTime = 0
floatTimer = None
drift = {}

# Layout Settings
nodeBuffer = 60
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



class NodeCircle(QGraphicsEllipseItem):
    def __init__(self, name, x, y, w, h):
        super().__init__(x, y, w, h)
        self.name = name

    def mousePressEvent(self, event):
        clickNode(self.name)


def confidenceColor(confidence):
    t = max(0, min(confidence, 100)) / 100
    hue = int(t * 120)
    return QColor.fromHsv(hue, 200, 220)


# sets the fill and keeps the glow the same color as the node
def colorNode(name, confidence):
    shownConfidence[name] = confidence
    color = confidenceColor(confidence)
    nodeCircles[name].setBrush(color)

    x, y = nodes[name]["x"], nodes[name]["y"]
    gradient = QRadialGradient(x, y, glowRadius)
    gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), glowAlpha))
    gradient.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), glowAlpha // 2))
    gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
    nodeGlows[name].setBrush(gradient)

def spot(name):
    return nodes[name]["x"] + drift[name]["dx"], nodes[name]["y"] + drift[name]["dy"]



def floatNodes():
    global floatTime
    floatTime += 0.03
    for name, d in drift.items():
        d["dx"] = math.sin(floatTime * d["speed"] + d["phase"]) * floatSize
        d["dy"] = math.cos(floatTime * d["speed"] * 0.8 + d["phase"]) * floatSize
        nodeCircles[name].setPos(d["dx"], d["dy"])
    for pair, line in connectionLines.items():
        if pair not in connectionQueue:
            x1, y1 = spot(pair[0])
            x2, y2 = spot(pair[1])
            line.setLine(x1, y1, x2, y2)




def fadeNode(name, confidence):
    targetConfidence[name] = confidence
    old = shownConfidence[name]
    if old == confidence:
        return
    if name in nodeFades:
        nodeFades[name].stop()
    anim = QVariantAnimation()
    anim.setDuration(600)
    anim.setEasingCurve(QEasingCurve.InOutCubic)
    anim.setStartValue(float(old))
    anim.setEndValue(float(confidence))
    anim.valueChanged.connect(lambda v: colorNode(name, v))
    nodeFades[name] = anim
    anim.start()

def clickNode(name):
    global selected
    if selected == name:
        selected = None
    else:
        selected = name
    showSelected()


def nodeTip(name):
    info = factInfo[name]
    count = 0
    for pair, line in connectionLines.items():
        if line.isVisible() and name in pair:
            count += 1
    conf = round(targetConfidence.get(name, 0))
    gap = "&nbsp;&nbsp;|&nbsp;&nbsp;"
    return (f"<b>Fact {name}</b>{gap}{info['text']}{gap}{info['topic']}<br>"
            f"Confidence: {conf}%<br>"
            f"Connections: {count}")


def removeBox():
    global infoBox
    if infoBox is not None and infoBox.scene() is not None:
        infoBox.scene().removeItem(infoBox)
    infoBox = None


def makeBox(name):
    global infoBox
    circle = nodeCircles[name]
    text = QGraphicsTextItem()
    text.setHtml(nodeTip(name))
    text.setDefaultTextColor(QColor(255, 255, 255))
    text.setTextWidth(210)
    size = text.boundingRect()

    box = QGraphicsRectItem(0, 0, size.width(), size.height(), circle)
    box.setBrush(QColor(20, 20, 20, 235))
    box.setPen(QPen(QColor(120, 120, 120), 1))
    box.setAcceptedMouseButtons(Qt.NoButton)
    text.setParentItem(box)
    text.setAcceptedMouseButtons(Qt.NoButton)

    x, y = nodes[name]["x"], nodes[name]["y"]
    area = circle.scene().sceneRect()
    boxX = x + 20
    if boxX + size.width() > area.right():
        boxX = x - 20 - size.width()
    boxY = max(area.top(), min(y - size.height() / 2, area.bottom() - size.height()))
    box.setPos(boxX, boxY)
    infoBox = box


def showSelected():
    removeBox()
    if selected is None:
        for circle in nodeCircles.values():
            circle.setOpacity(1)
            circle.setZValue(0)
        for line in connectionLines.values():
            line.setOpacity(1)
        return

    friends = {selected}
    for pair, line in connectionLines.items():
        if selected in pair and line.isVisible():
            friends.update(pair)

    for name, circle in nodeCircles.items():
        circle.setOpacity(1 if name in friends else 0.15)
        circle.setZValue(10 if name == selected else 0)
    for pair, line in connectionLines.items():
        line.setOpacity(1 if selected in pair else 0.1)
    makeBox(selected)


# Draws nodes
def drawNodes(scene):
    global floatTimer
    radius = 10
    for name, data in nodes.items():
        circle = NodeCircle(name, data["x"] - radius, data["y"] - radius, radius * 2, radius * 2)
        circle.setPen(QPen(QColor(255, 255, 255), .5))
        scene.addItem(circle)
        # glow is a child so it hides and shows with the node
        glow = QGraphicsEllipseItem(data["x"] - glowRadius, data["y"] - glowRadius, glowRadius * 2, glowRadius * 2, circle)
        glow.setPen(QPen(Qt.NoPen))
        glow.setFlag(QGraphicsItem.ItemStacksBehindParent)
        nodeGlows[name] = glow
        nodeCircles[name] = circle
        drift[name] = {"dx": 0, "dy": 0, "phase": random.uniform(0, 6.28), "speed": random.uniform(0.6, 1.4)}
        colorNode(name, data["confidence"])
        circle.setVisible(data["taught"])

    if floatTimer is None:
        floatTimer = QTimer()
        floatTimer.timeout.connect(floatNodes)
        floatTimer.start(30)


def farEnough(x, y):
    for other in nodes.values():
        if math.hypot(x - other["x"], y - other["y"]) < nodeBuffer:
            return False
    return True


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
        baseX = margin + topics.index(fact["topic"]) * columnSpacing + offset * 40
        baseY = margin + (fact["lesson"] - 1) * rowSpacing + offset * 40
        for tries in range(100):
            spread = 35 + tries
            x = baseX + random.randint(-spread, spread)
            y = baseY + random.randint(-spread, spread)
            if farEnough(x, y):
                break
        nodes[fact["id"]] = {"x": x, "y": y, "confidence": 0, "taught": False}
        factInfo[fact["id"]] = {"text": fact["questions"][0] + " " + fact["answer"], "topic": fact["topic"], "lesson": fact["lesson"]}

    for pair in links:
        connections[tuple(pair)] = 0

def clearGraph():
    global selected, infoBox
    selected = None
    infoBox = None
    nodes.clear()
    connections.clear()
    history.clear()
    nodeCircles.clear()
    nodeGlows.clear()
    factInfo.clear()
    targetConfidence.clear()
    shownConfidence.clear()
    for anim in nodeFades.values():
        anim.stop()
    nodeFades.clear()
    drift.clear()
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
        fadeNode(name, data["confidence"])
        nodeCircles[name].setVisible(data["taught"])
    showSelected()


# Updates connection strengths and updates each line so weaker connections are thinner and more transperant
def connectionLine(pair):
    x1, y1 = spot(pair[0])
    connectionLines[pair].setLine(x1, y1, x1, y1)
    connectionQueue.append(pair)
    if len(connectionQueue) == 1:
        drawNextLine()


def drawNextLine():
    pair = connectionQueue[0]
    line = connectionLines[pair]
    animation = QVariantAnimation()
    animation.setDuration(360)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.valueChanged.connect(lambda t: moveLine(pair, line, t))
    animation.finished.connect(lineFinished)
    connectionAnimations.append(animation)
    animation.start()


def moveLine(pair, line, t):
    x1, y1 = spot(pair[0])
    x2, y2 = spot(pair[1])
    line.setLine(x1, y1, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)



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
    showSelected()




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
        fadeNode(name, data["confidence"])
        nodeCircles[name].setVisible(data["taught"])
    showSelected()
