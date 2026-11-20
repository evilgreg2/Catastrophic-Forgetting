import math
import random
from PySide6.QtCore import QEasingCurve, QVariantAnimation, QTimer, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QRadialGradient
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from panda3d.core import CardMaker, ColorBlendAttrib, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, LineSegs, Material, NodePath, PNMImage, Texture, TransparencyAttrib
import graph
from graph import nodes, connections, factInfo


# Node Settings
nodeSize = 16
balls = {}
glows = {}
lines = {}
scene3d = None
glowScale = 3
glowStrength = 0.7
hoverGrow = 1.2
hoverName = None
hoverAnims = {}
hoverScale = {}
nodeCircles = {}
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
infoBox = None
clickedNode = False
infoSpot = (0, 0)
pulseQueue = []
pulseAnim = None
targetConfidence = {}

# Float Settings
floatSize = 4
floatTime = 0
floatTimer = None
drift = {}

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
        global clickedNode
        clickedNode = True
        clickNode(self.name)


def confidenceColor(confidence):
    t = max(0, min(confidence, 100)) / 100
    hue = int(t * 120)
    return QColor.fromHsv(hue, 200, 220)


# same color as above but in the 0 to 1 form panda wants
def ballColor(confidence):
    c = confidenceColor(confidence)
    return c.redF(), c.greenF(), c.blueF(), 1


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
    if infoBox is not None:
        infoBox.setPos(infoSpot[0] + drift[selected]["dx"], infoSpot[1] + drift[selected]["dy"])
    for pair, line in connectionLines.items():
        if pair not in connectionQueue:
            x1, y1 = spot(pair[0])
            x2, y2 = spot(pair[1])
            line.setLine(x1, y1, x2, y2)




def fadeNode(name, confidence):
    targetConfidence[name] = confidence
    # a new node just shows up with its right color, no fade from red
    if balls[name].isHidden():
        if name in nodeFades:
            nodeFades[name].stop()
        paintBall(name, confidence)
        return
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
    anim.valueChanged.connect(lambda v: paintBall(name, v))
    nodeFades[name] = anim
    anim.start()

def sceneClicked():
    global selected, clickedNode
    if clickedNode:
        clickedNode = False
        return
    selected = None
    showSelected()


def startPulse(names):
    global pulseAnim
    if pulseAnim is not None:
        pulseAnim.stop()
    for circle in nodeCircles.values():
        circle.setScale(1)
    pulseQueue.clear()
    pulseQueue.extend(names)
    nextPulse()


def nextPulse():
    global pulseAnim
    if not pulseQueue:
        pulseAnim = None
        return
    name = pulseQueue.pop(0)
    circle = nodeCircles[name]
    anim = QVariantAnimation()
    anim.setDuration(320)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.valueChanged.connect(lambda t: circle.setScale(1 + 0.11 * math.sin(t * math.pi)))
    anim.finished.connect(lambda: pulseDone(anim, circle))
    pulseAnim = anim
    anim.start()


def pulseDone(anim, circle):
    if anim is not pulseAnim:
        return
    circle.setScale(1)
    nextPulse()



def clickNode(name):
    global selected
    if selected == name:
        selected = None
    else:
        selected = name
    showSelected()

    if selected is None:
        return
    order = [name]
    for pair, line in connectionLines.items():
        if name in pair and line.isVisible():
            other = pair[0] if pair[1] == name else pair[1]
            if other not in order and nodeCircles[other].isVisible():
                order.append(other)
    startPulse(order)


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
    global infoBox, infoSpot
    circle = nodeCircles[name]
    text = QGraphicsTextItem()
    text.setHtml(nodeTip(name))
    text.setDefaultTextColor(QColor(255, 255, 255))
    text.setTextWidth(210)
    size = text.boundingRect()

    box = QGraphicsRectItem(0, 0, size.width(), size.height())
    circle.scene().addItem(box)
    box.setZValue(100)
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
    infoSpot = (boxX, boxY)
    box.setPos(boxX + drift[name]["dx"], boxY + drift[name]["dy"])
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


# the sphere that comes with panda is only about 12 sides so it looked rough, this makes a smooth one
def makeSphere(rings=32, slices=32):
    vdata = GeomVertexData("sphere", GeomVertexFormat.getV3n3(), Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(slices + 1):
            theta = 2 * math.pi * j / slices
            x = math.sin(phi) * math.cos(theta)
            y = math.sin(phi) * math.sin(theta)
            z = math.cos(phi)
            vertex.addData3(x, y, z)
            normal.addData3(x, y, z)

    tris = GeomTriangles(Geom.UHStatic)
    for i in range(rings):
        for j in range(slices):
            a = i * (slices + 1) + j
            b = a + slices + 1
            tris.addVertices(a, a + 1, b)
            tris.addVertices(a + 1, b + 1, b)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("sphere")
    node.addGeom(geom)
    return NodePath(node)


# soft white blob that fades out to nothing at the edge, used for the glow
def makeGlowCard():
    size = 128
    img = PNMImage(size, size, 4)
    img.fill(1, 1, 1)
    for x in range(size):
        for y in range(size):
            d = math.hypot(x - size / 2, y - size / 2) / (size / 2)
            img.setAlpha(x, y, max(0, 1 - d) ** 2)
    tex = Texture()
    tex.load(img)

    maker = CardMaker("glow")
    maker.setFrame(-1, 1, -1, 1)
    card = NodePath(maker.generate())
    card.setTexture(tex)
    return card


def growBall(name, target):
    if name in hoverAnims:
        hoverAnims[name].stop()
    anim = QVariantAnimation()
    anim.setDuration(180)
    anim.setEasingCurve(QEasingCurve.InOutCubic)
    anim.setStartValue(hoverScale.get(name, 1.0))
    anim.setEndValue(float(target))
    anim.valueChanged.connect(lambda v: sizeBall(name, v))
    hoverAnims[name] = anim
    anim.start()


def sizeBall(name, v):
    hoverScale[name] = v
    balls[name].setScale(nodeSize * v)


def hoverNode(name):
    global hoverName
    if name == hoverName:
        return
    if hoverName is not None:
        growBall(hoverName, 1)
    hoverName = name
    if name is not None:
        growBall(name, hoverGrow)


def hoverRay(ray):
    found, best = None, None
    if ray is not None:
        start, aim = ray
        aim.normalize()
        for name, ball in balls.items():
            if ball.isHidden():
                continue
            off = ball.getPos() - start
            t = off.dot(aim)
            if t < 0 or off.lengthSquared() - t * t > nodeSize * nodeSize:
                continue
            if best is None or t < best:
                found, best = name, t
    hoverNode(found)


# colors the ball and its glow, used whenever confidence changes
def paintBall(name, confidence):
    shownConfidence[name] = confidence
    r, g, b, a = ballColor(confidence)
    balls[name].setColor(r, g, b, 1)
    # emission keeps the dark side from going black
    mat = Material()
    mat.setEmission((r * 0.3, g * 0.3, b * 0.3, 1))
    balls[name].setMaterial(mat)
    glows[name].setColor(r, g, b, glowStrength)


# Draws nodes
def drawNodes(view):
    global scene3d
    scene3d = view.base.render
    sphere = makeSphere()
    glowCard = makeGlowCard()
    for name, data in nodes.items():
        ball = sphere.copyTo(view.base.render)
        ball.setScale(nodeSize)
        ball.setPos(*graph.worldPos(data))

        # glow is a card that always faces the camera and sits on top of whatever is behind it
        glow = glowCard.copyTo(ball)
        glow.setScale(glowScale)
        glow.setBillboardPointEye()
        glow.setLightOff()
        glow.setDepthWrite(False)
        glow.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
        glow.setBin("fixed", 0)
        glows[name] = glow
        balls[name] = ball
        paintBall(name, data["confidence"])
        if not data["taught"]:
            ball.hide()
    view.frameWeb()


def clearGraph():
    global selected, infoBox, pulseAnim, hoverName
    graph.clearGraph()
    selected = None
    infoBox = None
    if pulseAnim:
        pulseAnim.stop()
    pulseAnim = None
    pulseQueue.clear()
    for a in nodeFades.values():
        a.stop()
    for a in connectionAnimations:
        a.stop()
    for a in hoverAnims.values():
        a.stop()
    hoverAnims.clear()
    hoverScale.clear()
    hoverName = None
    nodeFades.clear()
    connectionAnimations.clear()
    connectionQueue.clear()
    for ball in balls.values():
        ball.removeNode()
    balls.clear()
    glows.clear()
    for line in lines.values():
        line.removeNode()
    lines.clear()
    nodeCircles.clear()
    nodeGlows.clear()
    connectionLines.clear()
    targetConfidence.clear()
    shownConfidence.clear()
    drift.clear()


def showNodes():
    for name, data in nodes.items():
        balls[name].setPos(*graph.worldPos(data))
        fadeNode(name, data["confidence"])
        if data["taught"]:
            balls[name].show()
        else:
            balls[name].hide()


# how thick and see through a line is, weaker connections are thinner and fainter
def lineLook(strength):
    t = max(0, min(1, (strength - cutoff) / (100 - cutoff)))
    width = minWidth + (maxWidth - minWidth) * t
    alpha = int(minAlpha + (maxAlpha - minAlpha) * t)
    return width, alpha


# draws (or redraws) the line for one pair, t is how far along it is so it can grow out of the first node
def drawLine(pair, strength, t=1.0, source=None):
    source = source or nodes
    if pair in lines:
        lines[pair].removeNode()
    x1, y1, z1 = graph.worldPos(source[pair[0]])
    x2, y2, z2 = graph.worldPos(source[pair[1]])
    width, alpha = lineLook(strength)

    # start and end at the edge of each ball so nothing shows inside them
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
    ux, uy, uz = dx / length, dy / length, dz / length
    sx, sy, sz = x1 + ux * nodeSize, y1 + uy * nodeSize, z1 + uz * nodeSize
    ex, ey, ez = x2 - ux * nodeSize, y2 - uy * nodeSize, z2 - uz * nodeSize

    seg = LineSegs()
    seg.setThickness(width)
    seg.setColor(1, 1, 1, alpha / 255)
    seg.moveTo(sx, sy, sz)
    seg.drawTo(sx + (ex - sx) * t, sy + (ey - sy) * t, sz + (ez - sz) * t)
    line = scene3d.attachNewNode(seg.create())
    line.setLightOff()
    line.setTransparency(TransparencyAttrib.MAlpha)
    lines[pair] = line


# new lines grow out one at a time
def connectionLine(pair):
    connectionQueue.append(pair)
    if len(connectionQueue) == 1:
        drawNextLine()


def drawNextLine():
    pair = connectionQueue[0]
    animation = QVariantAnimation()
    animation.setDuration(360)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.valueChanged.connect(lambda t: drawLine(pair, connections[pair], t))
    animation.finished.connect(lineFinished)
    connectionAnimations.append(animation)
    animation.start()


def lineFinished():
    if connectionQueue:
        connectionQueue.pop(0)
    if connectionQueue:
        drawNextLine()


def showConnections():
    for pair, strength in connections.items():
        if pair in connectionQueue:
            continue
        if strength < cutoff:
            if pair in lines:
                lines[pair].hide()
        elif pair not in lines or lines[pair].isHidden():
            connectionLine(pair)
        else:
            drawLine(pair, strength)



# Shows older node and connection data by indexing saved history from the updateNodes function
def readHistory(sliderValue):
    saved = graph.readHistory(sliderValue)
    if saved is None:
        return
    for name, data in saved["nodes"].items():
        balls[name].setPos(*graph.worldPos(data))
        fadeNode(name, data["confidence"])
        if data["taught"]:
            balls[name].show()
        else:
            balls[name].hide()
    for pair, strength in saved["connections"].items():
        if strength >= cutoff:
            drawLine(pair, strength, 1.0, saved["nodes"])
        elif pair in lines:
            lines[pair].hide()
