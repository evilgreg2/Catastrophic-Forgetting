import math
from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtGui import QColor

from panda3d.core import AntialiasAttrib, DynamicTextFont, Filename, SamplerState, CardMaker, ColorBlendAttrib, LineSegs, NodePath, Point2, Texture, TextNode, TransparencyAttrib, Vec3
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
infoBox3d = None
haloSize = 4
glowStrength = 0.6
hoverGrow = 1.2
hoverName = None
hoverAnims = {}
hoverScale = {}
connectionQueue = []
connectionAnimations = []
shownConfidence = {}
nodeFades = {}
selected = None
targetConfidence = {}

# Connection Settings
cutoff = 10
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
    sizeInfoBox()


# box shrinks slower than the scene when zooming out so the text stays readable
def sizeInfoBox():
    if infoBox3d is not None:
        scale = (view3d.zoomDist / view3d.refDist) ** 0.6
        infoBox3d.setScale(scale)
        infoBox3d.find("body").setX(nodeSize * 2.5 * (1 / scale - 1))


# size of the info box in 3d units, the balls are about 16 across for comparison
boxWidth = 280

textFont = None


# sharper font so the text still reads when zoomed out
def loadFont(path):
    global textFont
    textFont = DynamicTextFont(Filename.fromOsSpecific(str(path)))
    textFont.setPixelsPerUnit(64)
    textFont.setPageSize(1024, 1024)
    textFont.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    textFont.setMagfilter(SamplerState.FT_linear)
    textFont.setAnisotropicDegree(4)


# subject, then the fact, then the confidence
def makeInfoBox(name):
    global infoBox3d
    removeInfoBox()
    info = factInfo[name]
    holder = scene3d.attachNewNode("infoBox")
    holder.setPos(balls[name].getPos())
    holder.setBillboardPointEye()
    holder.setTransparency(TransparencyAttrib.MAlpha)
    holder.setDepthTest(False)
    holder.setDepthWrite(False)
    body = holder.attachNewNode("body")

    textScale = 16
    pad = 14
    left = nodeSize * 2.5
    conf = round(targetConfidence.get(name, 0))

    words = TextNode("words")
    words.setText(info["topic"] + "\n" + info["text"] + "\n" + f"Confidence: {conf}%")
    words.setWordwrap((boxWidth - pad * 2) / textScale)
    if textFont:
        words.setFont(textFont)
    words.setTextColor(1, 1, 1, 1)
    words.setShadow(0.06, 0.06)
    words.setShadowColor(0, 0, 0, 1)
    words.setAlign(TextNode.ALeft)
    textNp = body.attachNewNode(words)
    textNp.setScale(textScale)
    textNp.setAntialias(AntialiasAttrib.MMultisample)
    textNp.setBin("fixed", 32)

    # box grows with the text
    boxHeight = words.getHeight() * textScale + pad * 2
    top = boxHeight / 2
    textNp.setPos(left + pad, 0, top - pad - textScale * 0.8)

    border = CardMaker("border")
    border.setFrame(left - 4, left + boxWidth + 4, -top - 4, top + 4)
    edge = body.attachNewNode(border.generate())
    edge.setColor(0.5, 0.5, 0.55, 1)
    edge.setBin("fixed", 30)

    fill = CardMaker("fill")
    fill.setFrame(left, left + boxWidth, -top, top)
    back = body.attachNewNode(fill.generate())
    back.setColor(0.06, 0.06, 0.08, 0.92)
    back.setBin("fixed", 31)
    infoBox3d = holder
    sizeInfoBox()


def removeInfoBox():
    global infoBox3d
    if infoBox3d is not None:
        infoBox3d.removeNode()
    infoBox3d = None


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
    if selected is None:
        removeInfoBox()
    else:
        makeInfoBox(selected)


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


# Draws nodes
def drawNodes(view):
    global scene3d, view3d
    scene3d = view.base.render
    view3d = view
    view.onClick = clicked
    view.onZoom = updateLineWidths
    glowCard = makeGlow()
    discCard = makeDisc()
    for name, data in nodes.items():
        ball = view.base.render.attachNewNode("ball")
        ball.setScale(nodeSize)
        ball.setPos(*graph.worldPos(data))

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
        balls[name] = ball
        paintBall(name, data["confidence"])
        if not data["taught"]:
            ball.hide()
    view.autoFit = True


def clearGraph():
    global selected, hoverName
    graph.clearGraph()
    selected = None
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
    discs.clear()
    removeInfoBox()
    for line in lines.values():
        line.removeNode()
    lines.clear()
    lineWidths.clear()
    targetConfidence.clear()
    shownConfidence.clear()


def showNodes():
    for name, data in nodes.items():
        balls[name].setPos(*graph.worldPos(data))
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
    line.setTransparency(TransparencyAttrib.MAlpha)
    line.setDepthWrite(False)
    lines[pair] = line
    lineWidths[pair] = width
    styleLine(pair)


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
    showSelected()


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
    showSelected()
