import math
import random
import time

import numpy as np

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
nodeGap = 420
nodeBuffer = 300
upBias = 0.5
startRadius = 700
heightScale = 1.8
focalLength = 900

# Camera Settings
turnSpeed = 0.4
zoomStep = 0.9
walkSpeed = 0.4
fitFill = 1.5
backdropStrength = 0.1


def farEnough(x, y, z):
    for other in nodes.values():
        if math.dist((x, y, z), (other["x"], other["y"], other["baseZ"])) < nodeBuffer:
            return False
    return True


def loadGraph(facts, links):
    # each fact grows out of the first fact it links to, so every lesson builds off the last
    parents = {}
    for old, new in links:
        parents.setdefault(new, old)

    for fact in facts:
        parent = parents.get(fact["id"])
        for tries in range(300):
            if parent is None:
                x = random.uniform(-startRadius, startRadius)
                y = random.uniform(-startRadius, startRadius)
                z = random.uniform(-startRadius / 2, startRadius / 2)
            else:
                dx, dy, dz = random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1) + upBias
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                step = nodeGap * random.uniform(0.8, 1.2) * (1 + tries / 100)
                x = nodes[parent]["x"] + dx / length * step
                y = nodes[parent]["y"] + dy / length * step
                z = nodes[parent]["baseZ"] + dz / length * step
            if farEnough(x, y, z):
                break
        nodes[fact["id"]] = {"x": x, "y": y, "z": z, "baseZ": z, "confidence": 0, "taught": False}
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
        nodes[name]["z"] = nodes[name]["baseZ"] + newConfidence[name] * heightScale
        nodes[name]["taught"] = True

def updateConnections(newStrengths):
    connections.update(newStrengths)


def hazePixels(size):
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

    return (glow * 255 + np.random.random((size, size))).astype(np.uint8)


def worldPos(data):
    return data["x"], data["y"], data["z"]


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
        self.tx, self.ty, self.tz = 0, 0, 0
        self.keys = set()
        self.lastTime = time.perf_counter()
        self.last = None
        self.pressAt = None
        self.onClick = None
        self.onZoom = None
        self.refDist = self.dist
        self.zoomDist = self.dist
        self.autoFit = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.frame)
        self.timer.start(16)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def makeBackdrop(self):
        size = 1024
        gray = hazePixels(size)
        px = np.empty((size, size, 4), dtype=np.uint8)
        px[..., :3] = gray[..., None]
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
        # only the nodes taught so far, every spot twice (0% and 100% confidence) so it fits whatever confidence does
        pts = []
        for data in nodes.values():
            if data["taught"]:
                pts.append(Point3(data["x"], data["y"], data["baseZ"]))
                pts.append(Point3(data["x"], data["y"], data["baseZ"] + 100 * heightScale))
        low = [min(p[i] for p in pts) for i in range(3)]
        high = [max(p[i] for p in pts) for i in range(3)]
        self.tx, self.ty, self.tz = [(low[i] + high[i]) / 2 for i in range(3)]
        self.spin = 0
        self.tilt = 30
        self.dist = 3 * max(high[i] - low[i] for i in range(3))
        for _ in range(4):
            self.placeCam()
            lens = self.cam.node().getLens()
            w, h = lens.getFilmSize()
            far = 0
            for p in pts:
                q = self.cam.getRelativePoint(self.base.render, p)
                if q.y <= 0:
                    continue
                far = max(far, abs(q.x) * focalLength * 2 / (q.y * w), abs(q.z) * focalLength * 2 / (q.y * h))
            self.dist *= far / fitFill
        self.refDist = self.dist
        self.zoomDist = self.dist
        self.autoFit = True
        self.placeCam()

    def placeCam(self):
        s, t = math.radians(self.spin), math.radians(self.tilt)
        flat = math.cos(t) * self.dist
        self.cam.setPos(self.tx + math.sin(s) * flat, self.ty - math.cos(s) * flat, self.tz + math.sin(t) * self.dist)
        up = Vec3(-math.sin(s) * math.sin(t), math.cos(s) * math.sin(t), math.cos(t))
        self.cam.lookAt(Point3(self.tx, self.ty, self.tz), up)
        # clipping planes follow the zoom, fixed ones made everything vanish when zoomed far in or out
        self.cam.node().getLens().setNearFar(self.dist * 0.01, self.dist * 10 + 20000)

    def viewDir(self):
        s, t = math.radians(self.spin), math.radians(self.tilt)
        return Vec3(-math.sin(s) * math.cos(t), math.cos(s) * math.cos(t), -math.sin(t))

    # how far away the closest node near the middle of the screen is, None if there isn't one
    def lookedAt(self):
        fwd = self.viewDir()
        pos = self.cam.getPos()
        best = None
        for data in nodes.values():
            if not data["taught"]:
                continue
            off = Point3(*worldPos(data)) - pos
            along = off.dot(fwd)
            if along <= 0 or (off - fwd * along).length() > along * 0.3:
                continue
            if best is None or along < best:
                best = along
        return best

    def walk(self):
        now = time.perf_counter()
        dt = min(now - self.lastTime, 0.1)
        self.lastTime = now
        if not self.keys:
            return
        self.autoFit = False
        s, t = math.radians(self.spin), math.radians(self.tilt)
        fwd = (Qt.Key_W in self.keys) - (Qt.Key_S in self.keys)
        side = (Qt.Key_D in self.keys) - (Qt.Key_A in self.keys)
        step = (self.lookedAt() or self.dist) * walkSpeed * dt
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
        # spin around the node in the middle of the screen, the camera itself stays put
        near = self.lookedAt()
        if near:
            self.tx, self.ty, self.tz = self.cam.getPos() + self.viewDir() * near
            self.dist = near
            self.placeCam()

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
        self.autoFit = False
        flip = 1 if math.cos(math.radians(self.tilt)) > 0 else -1
        self.spin -= (pos.x() - self.last.x()) * turnSpeed * flip
        self.tilt = (self.tilt + (pos.y() - self.last.y()) * turnSpeed) % 360
        self.last = pos
        self.placeCam()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        self.autoFit = False
        self.dist *= zoomStep ** steps
        self.zoomDist *= zoomStep ** steps
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
