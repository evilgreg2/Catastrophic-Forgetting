
from math import sqrt
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


nodes = {
    "Node_A": {"x": 100, "y": 150, "confidence": 45},
    "Node_B": {"x": 300, "y": 100, "confidence": 85},
    "Node_C": {"x": 500, "y": 200, "confidence": 0},
    "Node_D": {"x": 200, "y": 350, "confidence": 30},
}

connections = [
    ("Node_A", "Node_B"),
    ("Node_B", "Node_C"),
    ("Node_A", "Node_D")
        ]

neighbors = {name: [] for name in nodes}
for a, b in connections:
    neighbors[a].append(b)
    neighbors[b].append(a)


for name, data in nodes.items():
    x = data["x"]
    y = data["y"]
    confidence = data["confidence"]
    linked_to = neighbors[name]
    print(name, x, y, confidence, linked_to)


def connectNodes(scene, nodeA, nodeB):
    nodeAX, nodeAY =  nodes[nodeA]["x"], nodes[nodeA]["y"]
    nodeBX, nodeBY =  nodes[nodeB]["x"], nodes[nodeB]["y"]
    print("Node AX, Node AY are:")
    print(nodeAX)
    print(nodeAY)

    # Calculate distance using the distance formula
    distance = sqrt(abs((nodeBX - nodeAX)**2 + (nodeBY - nodeAY)**2))

    if distance <=  150:
        scene.addLine(nodeAX, nodeAY, nodeBX, nodeBY, QPen(QColor(255, 255, 255), 2))



def drawNodes(scene):
    radius = 10
    for name, data in nodes.items():
        circle = scene.addEllipse(data["x"] - radius, data["y"] - radius, radius * 2, radius * 2, QPen(QColor(255, 255, 255), 2))
        circle.setBrush(QColor(255, 255, 255))






