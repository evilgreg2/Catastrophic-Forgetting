
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
