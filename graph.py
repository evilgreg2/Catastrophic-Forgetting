import math
import random
import time

from panda3d.core import loadPrcFileData
loadPrcFileData("", "window-type offscreen\nwin-size 1000 600\naudio-library-name null")

from direct.showbase.ShowBase import ShowBase
from panda3d.core import AntialiasAttrib, Camera, CardMaker, FrameBufferProperties, GraphicsOutput, GraphicsPipe, NodePath, OrthographicLens, Point2, Point3, Texture, Vec3, WindowProperties
from PySide6.QtCore import Qt, QTimer, Signal
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
spread = 0.6
heightScale = 3
depthScale = 2.2
focalLength = 900
center = (0, 0)

# Camera Settings
turnSpeed = 0.4
zoomStep = 0.9
walkSpeed = 0.4
fitFill = 0.95
backdropStrength = 0.1


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
        nodes[name]["z"] = newConfidence[name] * heightScale * spread
        nodes[name]["taught"] = True

def updateConnections(newStrengths):
    connections.update(newStrengths)


def worldPos(data):
    return (data["x"] - center[0]) * spread, (data["y"] - center[1]) * depthScale * spread, data["z"]


def readHistory(sliderValue):
    if not history:
        return None
    return history[max(0, min(sliderValue, len(history) - 1))]


class Graph3D(QWidget):
    moved = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
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
        self.backdrop = self.makeBackdrop()
        self.image = None

        self.spin = 0
        self.tilt = 30
        self.dist = 1000
        self.midZ = 0
        self.tx, self.ty, self.tz = 0, 0, 0
        self.keys = set()
        self.lastTime = time.perf_counter()
        self.last = None
        self.pressAt = None
        self.onClick = None
        self.onZoom = None
        self.refDist = self.dist

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.frame)
        self.timer.start(16)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def makeBackdrop(self):
        import numpy as np
        size = 1024
        axis = np.linspace(-1, 1, size)
        glow = backdropStrength * np.exp(-(np.hypot(axis[None, :], axis[:, None]) / 0.7) ** 2)

        # a few octaves of smooth blobs so the glow isn't a perfect circle
        rng = np.random.default_rng(7)
        haze = np.zeros((size, size))
        for cells, amp in ((3, 1), (6, 0.5), (12, 0.25)):
            grid = rng.random((cells + 2, cells + 2))
            pos = np.linspace(0, cells, size)
            i = pos.astype(int)
            f = pos - i
            f = f * f * (3 - 2 * f)
            rows = grid[i] * (1 - f)[:, None] + grid[i + 1] * f[:, None]
            haze += amp * (rows[:, i] * (1 - f) + rows[:, i + 1] * f)
        haze = (haze - haze.mean()) / haze.std()
        glow *= 1 + 0.25 * haze

        # sparse specks, a tiny bit brighter than the haze
        specks = rng.random((size, size)) > 0.9993
        glow += specks * rng.random((size, size)) * 0.1

        px = np.empty((size, size, 4), dtype=np.uint8)
        px[..., :3] = (glow * 255 + np.random.random((size, size)))[..., None].astype(np.uint8)
        px[..., 3] = 255
        tex = Texture()
        tex.setup2dTexture(size, size, Texture.TUnsignedByte, Texture.FRgba)
        tex.setRamImage(px.tobytes())

        root = NodePath("backdrop")
        lens = OrthographicLens()
        lens.setFilmSize(2, 2)
        cam = Camera("backdropCam")
        cam.setLens(lens)
        region = self.buf.makeDisplayRegion()
        region.setSort(-20)
        region.setCamera(root.attachNewNode(cam))
        maker = CardMaker("backdrop")
        maker.setFrame(-1, 1, -1, 1)
        card = root.attachNewNode(maker.generate())
        card.setTexture(tex)
        card.setY(5)
        card.setDepthTest(False)
        card.setDepthWrite(False)
        return root

    def shutdown(self):
        self.timer.stop()
        self.base.destroy()

    def frame(self):
        self.walk()
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
        self.midZ = 50 * heightScale * spread
        self.tx, self.ty, self.tz = 0, 0, self.midZ
        self.spin = 0
        self.tilt = 30
        self.dist = 1500
        top = 100 * heightScale * spread
        pts = [Point3(s[0], s[1], z) for s in spots for z in (0, top)]
        for _ in range(4):
            self.placeCam()
            lens = self.cam.node().getLens()
            far = 0
            for p in pts:
                f = Point2()
                if lens.project(self.cam.getRelativePoint(self.base.render, p), f):
                    far = max(far, abs(f.x), abs(f.y))
            self.dist *= far / fitFill
        self.refDist = self.dist
        self.placeCam()

    def placeCam(self):
        s, t = math.radians(self.spin), math.radians(self.tilt)
        flat = math.cos(t) * self.dist
        self.cam.setPos(self.tx + math.sin(s) * flat, self.ty - math.cos(s) * flat, self.tz + math.sin(t) * self.dist)
        up = Vec3(-math.sin(s) * math.sin(t), math.cos(s) * math.sin(t), math.cos(t))
        self.cam.lookAt(Point3(self.tx, self.ty, self.tz), up)

    def walk(self):
        now = time.perf_counter()
        dt = min(now - self.lastTime, 0.1)
        self.lastTime = now
        if not self.keys:
            return
        s, t = math.radians(self.spin), math.radians(self.tilt)
        fwd = (Qt.Key_W in self.keys) - (Qt.Key_S in self.keys)
        side = (Qt.Key_D in self.keys) - (Qt.Key_A in self.keys)
        step = self.dist * walkSpeed * dt
        self.tx += (-math.sin(s) * math.cos(t) * fwd + math.cos(s) * side) * step
        self.ty += (math.cos(s) * math.cos(t) * fwd + math.sin(s) * side) * step
        self.tz -= math.sin(t) * fwd * step
        self.placeCam()

    def keyPressEvent(self, event):
        if not event.isAutoRepeat():
            self.keys.add(event.key())

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self.keys.discard(event.key())

    def focusOutEvent(self, event):
        self.keys.clear()

    def mousePressEvent(self, event):
        self.last = event.position()
        self.pressAt = event.position()

    def mouseReleaseEvent(self, event):
        # barely moved means it was a click, not a drag
        pos = event.position()
        if self.onClick and abs(pos.x() - self.pressAt.x()) + abs(pos.y() - self.pressAt.y()) < 5:
            self.onClick(pos.x(), pos.y())

    def mouseRay(self, pos):
        near, far = Point3(), Point3()
        spot = Point2(pos.x() / self.width() * 2 - 1, 1 - pos.y() / self.height() * 2)
        self.cam.node().getLens().extrude(spot, near, far)
        near = self.base.render.getRelativePoint(self.cam, near)
        far = self.base.render.getRelativePoint(self.cam, far)
        return near, far - near

    def leaveEvent(self, event):
        self.moved.emit(None)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if not event.buttons() & Qt.LeftButton:
            self.moved.emit(self.mouseRay(pos))
            return
        flip = 1 if math.cos(math.radians(self.tilt)) > 0 else -1
        self.spin -= (pos.x() - self.last.x()) * turnSpeed * flip
        self.tilt = (self.tilt + (pos.y() - self.last.y()) * turnSpeed) % 360
        self.last = pos
        self.placeCam()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        self.dist *= zoomStep ** steps
        self.placeCam()
        if self.onZoom:
            self.onZoom()

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
