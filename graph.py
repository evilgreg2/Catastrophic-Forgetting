import math
import random

from panda3d.core import loadPrcFileData
loadPrcFileData("", "window-type offscreen\nwin-size 1000 600\naudio-library-name null")

from direct.showbase.ShowBase import ShowBase
from panda3d.core import GraphicsOutput, Texture
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

nodes = {}
connections = {}
history = []
factInfo = {}

# Layout Settings
nodeBuffer = 60
columnSpacing = 160
rowSpacing = 110


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
        nodes[name]["taught"] = True

def updateConnections(newStrengths):
    connections.update(newStrengths)


def readHistory(sliderValue):
    if not history:
        return None
    return history[max(0, min(sliderValue, len(history) - 1))]


class Graph3D(QWidget):
    def __init__(self):
        super().__init__()
        self.base = ShowBase()
        self.base.disableMouse()
        self.base.setBackgroundColor(0, 0, 0)

        self.tex = Texture()
        self.base.win.addRenderTexture(self.tex, GraphicsOutput.RTMCopyRam)
        self.image = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.frame)
        self.timer.start(16)

    def frame(self):
        self.base.taskMgr.step()
        data = self.tex.getRamImageAs("BGRA")
        if len(data) == 0:
            return
        raw = bytes(data)
        w, h = self.tex.getXSize(), self.tex.getYSize()
        self.image = QImage(raw, w, h, QImage.Format_RGB32).mirrored(False, True)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self.image:
            p.drawImage(self.rect(), self.image)
