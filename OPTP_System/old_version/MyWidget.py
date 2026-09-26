"""Here are some Widgets customized for specific GUI applications."""

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QRadialGradient, QColor, QPen
from PySide6.QtCore import Property, QPointF, Qt, QSize



#region LED indicator widget
class LedIndicator(QWidget):
    
    def __init__(self, parent = None):
        super().__init__(parent)    # initialize parent class
        self._status = False     # default status is off (False)
        self.setMinimumSize(10, 10)   # set fixed size for the LED indicator
        
    def paintEvent(self, event):
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing )  # enable anti-aliasing for smoother edges
        
        center = QPointF(self.width() / 2, self.height() / 2)   # center point of the widget
        radius = min(self.width(), self.height()) / 2 - 4   # radius of the LED circle
        gradient = QRadialGradient(center, radius)   # radial gradient for 3D effect
        
        # Set gradient colors based on status
        if self._status:
            gradient.setColorAt(0, QColor(144, 220, 144))   # bright green at center
            gradient.setColorAt(0.5, QColor(34, 200, 34))   # dark green at middle
            gradient.setColorAt(1, QColor(34, 150, 34))       # very dark green at edg
            pen_color = QColor(34, 139, 34, 200)            # semi-transparent dark green border
        else:
            gradient.setColorAt(0, QColor(90, 100, 90))   # light gray at center
            gradient.setColorAt(0.5, QColor(60, 70, 60)) # dark gray at middle
            gradient.setColorAt(1, QColor(30, 40, 30))   # very dark gray at edge
            pen_color = QColor(40, 50, 40, 200)          # semi-transparent dark gray border
            
        # Draw the LED circle with gradient fill
        painter.setBrush(gradient)                          # set brush to gradient
        painter.setPen(QPen(pen_color, 1))                  # set pen for border
        painter.drawEllipse(center, radius, radius)         # draw the circle with radius
        
        
        # Draw border
        border_pen = QPen(QColor(120, 120, 120, 255), 1)  # semi-transparent gray border
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius+1.5, radius+1.5)         # draw the circle with radius
        
        painter.end()
        
    @Property(bool)
    def status(self):
        """Get the current status of the LED indicator."""
        return self._status

    @status.setter
    def status(self, value):
        """Set the status of the LED indicator and update the display."""
        self._status = value
        self.update()   # trigger repaint to reflect status change
                
#endregion
        
        
        