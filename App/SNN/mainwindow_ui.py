# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mainwindow.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QGraphicsView, QMainWindow, QMenuBar,
    QPushButton, QSizePolicy, QStatusBar, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(802, 609)
        self.actionExport_As_Json = QAction(MainWindow)
        self.actionExport_As_Json.setObjectName(u"actionExport_As_Json")
        self.actionExport_Verilog = QAction(MainWindow)
        self.actionExport_Verilog.setObjectName(u"actionExport_Verilog")
        self.actionClose = QAction(MainWindow)
        self.actionClose.setObjectName(u"actionClose")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.buildButton = QPushButton(self.centralwidget)
        self.buildButton.setObjectName(u"buildButton")
        self.buildButton.setGeometry(QRect(310, 510, 161, 51))
        self.visualizerContainer = QGraphicsView(self.centralwidget)
        self.visualizerContainer.setObjectName(u"visualizerContainer")
        self.visualizerContainer.setGeometry(QRect(-10, 10, 811, 491))
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 802, 24))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.actionExport_As_Json.setText(QCoreApplication.translate("MainWindow", u"Export As Json", None))
        self.actionExport_Verilog.setText(QCoreApplication.translate("MainWindow", u"Export LayerMem", None))
        self.actionClose.setText(QCoreApplication.translate("MainWindow", u"Exit", None))
        self.buildButton.setText(QCoreApplication.translate("MainWindow", u"Build", None))
    # retranslateUi

