import math
import random
import time
from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtGui import QColor

from panda3d.core import SamplerState, CardMaker, ColorBlendAttrib, LineSegs, NodePath, Point2, Texture, TransparencyAttrib, Vec3
import graph
from graph import nodes, connections, factInfo


# Node Settings
nodeSize = 7.2
balls = {}
glows = {}
discs = {}
lines = {}
lineWidths = {}
scene3d = None
view3d = None
onSelect = None
haloSize = 4
glowStrength = 0.6
hoverGrow = 1.2
driftSize = 5
driftSpeed = 1.6
hoverName = None
hoverAnims = {}
hoverScale = {}
basePos = {}
phases = {}
lineArgs = {}
connectionQueue = []
connectionAnimations = []
shownConfidence = {}
nodeFades = {}
selected = None
targetConfidence = {}

# Connection Settings
cutoff = 0
minWidth = 0.5
maxWidth = 2
minAlpha = 50
maxAlpha = 255


def confidenceColor(confidence):
    t = max(0, min(confidence, 100)) / 100
    shade = int(60 + t * 195)
    return QColor(shade, shade, shade)


# same color as above but in the 0 to 1 form panda wants
def ballColor(confidence):
    c = confidenceColor(confidence)
    return c.redF(), c.greenF(), c.blueF(), 1


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


# every node that has a line showing to this one
def friendsOf(name):
    friends = {name}
    for pair, line in lines.items():
        if name in pair and not line.isHidden():
            friends.update(pair)
    return friends


# how thick a line is on screen, shrinks when you zoom out and grows when you zoom in
def lineThickness(pair):
    base = lineWidths[pair]
    if selected in pair:
        base += 1
    return max(1, base * view3d.refDist / view3d.zoomDist)


# the lines touching the selected node go solid white and on top of everything, the rest get really faint
def styleLine(pair):
    line = lines[pair]
    if selected is None:
        line.clearColor()
        line.clearColorScale()
        line.clearBin()
    elif selected in pair:
        line.setColor(1, 1, 1, 1)
        line.clearColorScale()
        line.setBin("fixed", -10)
    else:
        line.clearColor()
        line.setColorScale(1, 1, 1, 0.1)
        line.clearBin()
    line.setRenderModeThickness(lineThickness(pair), 1)


def updateLineWidths():
    for pair in lines:
        lines[pair].setRenderModeThickness(lineThickness(pair), 1)


def countNodes():
    count = 0
    for ball in balls.values():
        if not ball.isHidden():
            count += 1
    return count


def countConnections():
    count = 0
    for line in lines.values():
        if not line.isHidden():
            count += 1
    return count


onCount = lambda nodes, conns: None


# with a node selected only it and the nodes it connects to are counted
def updateCounts():
    if selected is None:
        return countNodes(), countConnections()
    conns = 0
    for pair, line in lines.items():
        if selected in pair and not line.isHidden():
            conns += 1
    return len(friendsOf(selected)), conns


def showSelected():
    friends = friendsOf(selected) if selected is not None else None
    for name, ball in balls.items():
        if friends is None or name in friends:
            ball.clearColorScale()
            glows[name].clearColorScale()
            if name == selected:
                ball.setScale(nodeSize * 1.3)
                glows[name].setColorScale(1.4, 1.4, 1.4, 1.4)
            else:
                ball.setScale(nodeSize)
        else:
            ball.setScale(nodeSize)
            ball.setColorScale(0.2, 0.2, 0.2, 1)
            glows[name].setColorScale(0.2, 0.2, 0.2, 0.15)
    for pair in lines:
        styleLine(pair)
    onCount(*updateCounts())
    if selected is None:
        onSelect("")
        return
    info = factInfo[selected]
    onSelect(f"{info['topic']}\n\n{info['text']}\n\nConfidence: {round(targetConfidence.get(selected, 0))}%")


# works out which ball is under the mouse by projecting each one onto the screen
# mx and my are in widget pixels, returns the name or None if you clicked empty space
def pickNode(mx, my):
    lens = view3d.cam.node().getLens()
    w, h = view3d.width(), view3d.height()
    best, bestDepth = None, None
    for name, ball in balls.items():
        if ball.isHidden():
            continue
        p = view3d.cam.getRelativePoint(scene3d, ball.getPos(scene3d))
        center, edge = Point2(), Point2()
        if not lens.project(p, center):
            continue
        lens.project(p + Vec3(nodeSize, 0, 0), edge)
        sx = (center.x + 1) / 2 * w
        sy = (1 - center.y) / 2 * h
        radius = max(abs(edge.x - center.x) / 2 * w, 10)
        if math.hypot(mx - sx, my - sy) <= radius and (bestDepth is None or p.y < bestDepth):
            best, bestDepth = name, p.y
    return best


# clicking a ball selects it, clicking it again or empty space puts everything back
def clicked(mx, my):
    global selected
    name = pickNode(mx, my)
    selected = None if name is None or name == selected else name
    showSelected()


def makeCard(name, size, frame, alpha):
    import numpy as np
    axis = (np.arange(size) + 0.5 - size / 2) / (size / 2)
    d = np.hypot(axis[None, :], axis[:, None])
    a = np.arctan2(axis[:, None], axis[None, :])
    px = np.full((size, size, 4), 255, dtype=np.uint8)
    px[..., 3] = (np.clip(alpha(d, a, np), 0, 1) * 255).astype(np.uint8)
    tex = Texture()
    tex.setup2dTexture(size, size, Texture.TUnsignedByte, Texture.FRgba)
    tex.setRamImage(px.tobytes())
    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)

    maker = CardMaker(name)
    maker.setFrame(-frame, frame, -frame, frame)
    card = NodePath(maker.generate())
    card.setTexture(tex)
    return card


# soft glow around a dot, fades out the same way as the dots on the front page
def makeGlow():
    return makeCard("glow", 256, haloSize, lambda d, a, np: np.interp(d, [0, 0.35, 1], [0.35, 0.08, 0]))


# solid dot facing the camera, also covers any line running into the node
def makeDisc():
    return makeCard("disc", 512, 1.05, lambda d, a, np: (1 / 1.05 - d) * 256 + 0.5)


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
            if t < 0 or off.lengthSquared() - t * t > (nodeSize * 2) ** 2:
                continue
            if best is None or t < best:
                found, best = name, t
    hoverNode(found)


# colors the ring, used whenever confidence changes
def paintBall(name, confidence):
    shownConfidence[name] = confidence
    r, g, b, a = ballColor(confidence)
    discs[name].setColor(r, g, b, 1)
    glows[name].setColor(r, g, b, glowStrength)


def spot(name, base):
    t = time.perf_counter() * driftSpeed
    px, py, pz = phases[name]
    return base[0] + math.sin(t + px) * driftSize, base[1] + math.sin(t + py) * driftSize, base[2] + math.sin(t + pz) * driftSize


def moveBall(name, data):
    basePos[name] = graph.worldPos(data)
    balls[name].setPos(*spot(name, basePos[name]))


# nodes float around their real spot a tiny bit, the lines have to be redrawn to follow them
def drift():
    for name, base in basePos.items():
        balls[name].setPos(*spot(name, base))
    for pair, args in lineArgs.items():
        if pair not in connectionQueue and not lines[pair].isHidden():
            drawLine(pair, args[0], 1.0, args[1])


# Draws nodes
def drawNodes(view):
    global scene3d, view3d
    scene3d = view.base.render
    view3d = view
    view.onClick = clicked
    view.onZoom = updateLineWidths
    view.onFrame = drift
    glowCard = makeGlow()
    discCard = makeDisc()
    for name, data in nodes.items():
        ball = view.base.render.attachNewNode("ball")
        ball.setScale(nodeSize)
        phases[name] = [random.uniform(0, 6.28) for _ in range(3)]
        balls[name] = ball
        moveBall(name, data)

        disc = discCard.copyTo(ball)
        disc.setBillboardPointEye()
        disc.setTransparency(TransparencyAttrib.MMultisample)
        disc.setBin("fixed", -5)

        # glow is a card that always faces the camera and sits on top of whatever is behind it
        glow = glowCard.copyTo(ball)
        glow.setBillboardPointEye(0.5)
        glow.setDepthWrite(False)
        glow.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
        glow.setBin("fixed", -6)
        glows[name] = glow
        discs[name] = disc
        paintBall(name, data["confidence"])
        if not data["taught"]:
            ball.hide()
    view.autoFit = True


def clearGraph():
    global selected, hoverName
    graph.clearGraph()
    selected = None
    onSelect("")
    onCount(0, 0)
    for a in nodeFades.values():
        a.stop()
    for a in connectionAnimations:
        a.stop()
        a.deleteLater()
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
    discs.clear()
    for line in lines.values():
        line.removeNode()
    lines.clear()
    lineWidths.clear()
    lineArgs.clear()
    basePos.clear()
    phases.clear()
    targetConfidence.clear()
    shownConfidence.clear()


def showNodes():
    for name, data in nodes.items():
        moveBall(name, data)
        fadeNode(name, data["confidence"])
        if data["taught"]:
            balls[name].show()
        else:
            balls[name].hide()
    if view3d.autoFit:
        view3d.frameWeb()


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
    x1, y1, z1 = spot(pair[0], graph.worldPos(source[pair[0]]))
    x2, y2, z2 = spot(pair[1], graph.worldPos(source[pair[1]]))
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
    line.setTransparency(TransparencyAttrib.MAlpha)
    line.setDepthWrite(False)
    lines[pair] = line
    lineWidths[pair] = width
    lineArgs[pair] = (strength, None if source is nodes else source)
    styleLine(pair)


# new lines grow out one at a time
def connectionLine(pair):
    connectionQueue.append(pair)
    if len(connectionQueue) == 1:
        drawNextLine()


def drawNextLine():
    pair = connectionQueue[0]
    animation = QVariantAnimation(view3d)
    animation.setDuration(150)
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
    connectionAnimations.pop(0).deleteLater()
    if connectionQueue:
        drawNextLine()
    onCount(*updateCounts())


def showConnections():
    for pair, strength in connections.items():
        if pair in connectionQueue:
            continue
        # a link shows as soon as both its nodes are taught, strength only makes it fainter or brighter
        if not (nodes[pair[0]]["taught"] and nodes[pair[1]]["taught"]):
            continue
        if pair not in lines or lines[pair].isHidden():
            connectionLine(pair)
        else:
            drawLine(pair, strength)
    showSelected()


# Shows older node and connection data by indexing saved history from the updateNodes function
def readHistory(sliderValue):
    saved = graph.readHistory(sliderValue)
    if saved is None:
        return
    for name, data in saved["nodes"].items():
        moveBall(name, data)
        fadeNode(name, data["confidence"])
        if data["taught"]:
            balls[name].show()
        else:
            balls[name].hide()
    for pair, strength in saved["connections"].items():
        if pair in connectionQueue:
            continue
        if saved["nodes"][pair[0]]["taught"] and saved["nodes"][pair[1]]["taught"]:
            drawLine(pair, strength, 1.0, saved["nodes"])
        elif pair in lines:
            lines[pair].hide()
    showSelected()
