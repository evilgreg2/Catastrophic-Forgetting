import math
import random

from panda3d.core import loadPrcFileData
loadPrcFileData("", "window-type offscreen\nwin-size 1000 600\naudio-library-name null")

from direct.showbase.ShowBase import ShowBase
from panda3d.core import AntialiasAttrib, AmbientLight, DirectionalLight, FrameBufferProperties, GraphicsOutput, GraphicsPipe, Texture, WindowProperties
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

nodes = {}
connections = {}
history = []
factInfo = {}

# Layout Settings
nodeBuffer = 60
columnSpacing = 160
rowSpacing = 110
heightScale = 2.4
depthScale = 2.2
focalLength = 900
center = (0, 0)

# Camera Settings
turnSpeed = 0.4
zoomStep = 0.9


def farEnough(x, y):
    for other in nodes.values():
        if math.hypot(x - other["x"], y - other["y"]) < nodeBuffer:
            return False
    return True


def loadGraph(facts, links, width, height):
    global center
    center = (width / 2, height / 2)
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
        nodes[fact["id"]] = {"x": x, "y": y, "z": 0, "confidence": 0, "taught": False}
        factInfo[fact["id"]] = {"text": fact["questions"][0] + " " + fact["answer"], "topic": fact["topic"], "lesson": fact["lesson"]}

    for pair in links:
        connections[tuple(pair)] = 0


# Saves a copy of all node data and all connection strengths to history
def saveHistory():
    history.append({
        "nodes": {name: dict(data) for name, data in nodes.items()},
        "connections": dict(connections),
    })


def clearGraph():
    nodes.clear()
    connections.clear()
    factInfo.clear()
    history.clear()


def updateNodes(newConfidence):
    for name in newConfidence:
        nodes[name]["confidence"] = newConfidence[name]
        nodes[name]["z"] = newConfidence[name] * heightScale
        nodes[name]["taught"] = True

def updateConnections(newStrengths):
    connections.update(newStrengths)


def worldPos(data):
    return data["x"] - center[0], (data["y"] - center[1]) * depthScale, data["z"]


def readHistory(sliderValue):
    if not history:
        return None
    return history[max(0, min(sliderValue, len(history) - 1))]


class Graph3D(QWidget):
    def __init__(self):
        super().__init__()
        self.base = ShowBase()
        self.base.disableMouse()
        self.base.win.setActive(False)

        fb = FrameBufferProperties()
        fb.setRgbaBits(8, 8, 8, 8)
        fb.setDepthBits(24)
        fb.setMultisamples(4)
        flags = GraphicsPipe.BFRefuseWindow | GraphicsPipe.BFResizeable
        self.buf = self.base.graphicsEngine.makeOutput(self.base.pipe, "buf", -2, fb, WindowProperties.size(1000, 600), flags, self.base.win.getGsg(), self.base.win)
        self.buf.setClearColor((0, 0, 0, 1))
        self.base.render.setAntialias(AntialiasAttrib.MAuto)

        self.tex = Texture()
        self.buf.addRenderTexture(self.tex, GraphicsOutput.RTMCopyRam)
        self.cam = self.base.makeCamera(self.buf)

        amb = AmbientLight("amb")
        amb.setColor((0.35, 0.35, 0.4, 1))
        sun = DirectionalLight("sun")
        sun.setColor((0.7, 0.7, 0.65, 1))
        sunNode = self.base.render.attachNewNode(sun)
        sunNode.setHpr(-30, -50, 0)
        self.base.render.setLight(self.base.render.attachNewNode(amb))
        self.base.render.setLight(sunNode)
        self.image = None

        self.spin = 0
        self.tilt = 30
        self.dist = 1000
        self.near, self.far = 200, 4000
        self.midZ = 0
        self.last = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.frame)
        self.timer.start(16)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def shutdown(self):
        self.timer.stop()
        self.base.destroy()

    def frame(self):
        self.base.taskMgr.step()
        data = self.tex.getRamImageAs("BGRA")
        if len(data) == 0:
            return
        raw = bytes(data)
        w, h = self.tex.getXSize(), self.tex.getYSize()
        self.image = QImage(raw, w, h, QImage.Format_RGB32).mirrored(False, True)
        self.update()

    def frameWeb(self):
        spots = [worldPos(data) for data in nodes.values()]
        halfW = max(abs(s[0]) for s in spots)
        halfD = max(abs(s[1]) for s in spots)
        self.midZ = 50 * heightScale
        self.spin = 0
        self.tilt = 30
        tilt = math.radians(self.tilt)
        wide = halfW * 2.2 / self.width()
        tall = (halfD * math.sin(tilt) + self.midZ) * 2.2 / self.height()
        self.dist = focalLength * max(wide, tall) + halfD * math.cos(tilt)
        self.near, self.far = self.dist * 0.2, self.dist * 2.5
        self.placeCam()

    def placeCam(self):
        s, t = math.radians(self.spin), math.radians(self.tilt)
        flat = math.cos(t) * self.dist
        self.cam.setPos(math.sin(s) * flat, -math.cos(s) * flat, self.midZ + math.sin(t) * self.dist)
        self.cam.lookAt(0, 0, self.midZ)

    def mousePressEvent(self, event):
        self.last = event.position()

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.LeftButton:
            return
        pos = event.position()
        self.spin -= (pos.x() - self.last.x()) * turnSpeed
        self.tilt = max(5, min(85, self.tilt + (pos.y() - self.last.y()) * turnSpeed))
        self.last = pos
        self.placeCam()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        self.dist = max(self.near, min(self.far, self.dist * zoomStep ** steps))
        self.placeCam()

    def resizeEvent(self, event):
        r = self.devicePixelRatio()
        w, h = max(int(self.width() * r), 1), max(int(self.height() * r), 1)
        self.buf.setSize(w, h)
        lens = self.cam.node().getLens()
        lens.setFilmSize(w, h)
        lens.setFocalLength(focalLength)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self.image:
            p.drawImage(self.rect(), self.image)
