# SeisComP Inventory Editor GUI
#!/usr/bin/env python3

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QTreeWidget, QTreeWidgetItem,QTreeWidgetItemIterator, 
                           QLabel, QPushButton, QFileDialog, QMessageBox, QLineEdit,
                           QFormLayout, QGroupBox, QTabWidget, QStyle, QStatusBar, 
                           QFrame, QSplitter, QMenu, QAction, QShortcut)
from PyQt5.QtGui import QIcon, QPalette, QColor, QKeySequence  # Add QKeySequence here
from PyQt5.QtCore import Qt, QSettings, QTimer
from xml.etree import ElementTree as ET
from pathlib import Path
import copy
import re

class ValidationLineEdit(QLineEdit):
    def __init__(self, validator=None, required=False, parent=None):
        super().__init__(parent)
        self.validator = validator
        self.required = required
        self.textChanged.connect(self.validate)
        self.editingFinished.connect(self.on_editing_finished)
        self.setStyleSheet("""
            QLineEdit { padding: 5px; border: 1px solid #ccc; border-radius: 3px; }
            QLineEdit:focus { border-color: #66afe9; }
        """)
        
    def validate(self):
        if not self.text() and self.required:
            self.setStyleSheet("QLineEdit { background-color: #ffe6e6; }")
            return False
        if self.validator and self.text():
            if not self.validator(self.text()):
                self.setStyleSheet("QLineEdit { background-color: #ffe6e6; }")
                return False
        self.setStyleSheet("""
            QLineEdit { background-color: white; padding: 5px; border: 1px solid #ccc; border-radius: 3px; }
            QLineEdit:focus { border-color: #66afe9; }
        """)
        return True
        
    def on_editing_finished(self):
        if self.parent() and hasattr(self.parent(), 'handle_editing_finished'):
            self.parent().handle_editing_finished()

class TreeWidgetWithKeyboardNav(QTreeWidget):
    """Extended QTreeWidget with enhanced keyboard navigation"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        # Connect currentItemChanged signal to handle selection
        self.currentItemChanged.connect(self._handleCurrentItemChanged)
        
    def _handleCurrentItemChanged(self, current, previous):
        """Handle item selection when current item changes"""
        if current:
            self.itemClicked.emit(current, 0)
            
    def keyPressEvent(self, event):
        """Handle keyboard navigation events"""
        key = event.key()
        current_item = self.currentItem()
        
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            # Additional action for enter key if needed
            if current_item:
                self.itemClicked.emit(current_item, 0)
        elif key == Qt.Key_Right:
            if current_item and not current_item.isExpanded():
                current_item.setExpanded(True)
            else:
                # Move to first child if expanded
                if current_item and current_item.childCount() > 0:
                    self.setCurrentItem(current_item.child(0))
        elif key == Qt.Key_Left:
            if current_item:
                if current_item.isExpanded():
                    current_item.setExpanded(False)
                else:
                    # Move to parent
                    parent = current_item.parent()
                    if parent:
                        self.setCurrentItem(parent)
        elif key == Qt.Key_Home:
            # Move to first item
            first_item = self.topLevelItem(0)
            if first_item:
                self.setCurrentItem(first_item)
        elif key == Qt.Key_End:
            # Move to last visible item
            last_item = self.topLevelItem(self.topLevelItemCount() - 1)
            if last_item:
                while last_item.isExpanded() and last_item.childCount() > 0:
                    last_item = last_item.child(last_item.childCount() - 1)
                self.setCurrentItem(last_item)
        elif key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            # Handle vertical navigation
            super().keyPressEvent(event)
            # No need to emit itemClicked here as currentItemChanged will handle it
        else:
            # Handle all other keys
            super().keyPressEvent(event)


class SeisCompInventoryEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ns = {'sc3': 'http://geofon.gfz-potsdam.de/ns/seiscomp3-schema/0.12'}
        self.current_file = None
        self.tree = None
        self.root = None
        self.settings = QSettings('SeisCompEditor', 'InventoryEditor')
        self.unsaved_changes = False
        self.initUI()
        self.loadSettings()
        self.setupKeyboardNavigation()

        # Initialize autosave timer
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self.perform_autosave)

    def setupKeyboardNavigation(self):
        """Setup keyboard shortcuts and navigation"""
        # Add keyboard shortcuts for common actions
        shortcuts = {
            'Ctrl+O': self.load_xml,
            'Ctrl+S': self.save_xml,
            'Ctrl+Q': self.close,
            'F5': self.tree_widget.expandAll,
            'F6': self.tree_widget.collapseAll,
            'Ctrl+F': lambda: self.statusBar.showMessage('Search functionality coming soon...', 2000)
        }
        
        for key, action in shortcuts.items():
            # Use QKeySequence instead of QKeySequenceEdit
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
        
        # Enable tab navigation between form fields
        for tab in [self.network_tab, self.station_tab, self.location_tab, self.sensor_tab, self.datalogger_tab, self.stream_tab]:
            self.setupTabOrder(tab)
    
    def setupTabOrder(self, tab):
        """Setup tab order for form fields within a tab"""
        if not tab.layout():
            return
            
        widgets = []
        layout = tab.layout()
        
        # Check if it's a QFormLayout
        if isinstance(layout, QFormLayout):
            for i in range(layout.rowCount()):
                field = layout.itemAt(i, QFormLayout.FieldRole)
                if field and field.widget():
                    widgets.append(field.widget())
        
        # Set tab order
        for i in range(len(widgets) - 1):
            self.setTabOrder(widgets[i], widgets[i + 1])
        
        # Connect return/enter key to move to next field
        for widget in widgets:
            if isinstance(widget, QLineEdit):
                widget.returnPressed.connect(lambda w=widget: self.focusNextChild())

    def perform_autosave(self):
        """Perform the actual autosave"""
        if self.unsaved_changes and self.current_file:
            try:
                self.save_xml()
                self.statusBar.showMessage("Autosaved", 2000)
                self.autosave_label.setText("Changes Saved")
                self.autosave_label.setStyleSheet("color: green; padding: 2px 5px; border: 1px solid green; border-radius: 3px;")
            except Exception as e:
                self.statusBar.showMessage(f"Autosave failed: {str(e)}", 3000)
                self.autosave_label.setText("Save Failed")
                self.autosave_label.setStyleSheet("color: red; padding: 2px 5px; border: 1px solid red; border-radius: 3px;")




    def autosave_stream(self):
        """Trigger autosave with debounce"""
        if hasattr(self, 'current_element'):
            self.autosave_timer.start(1000)  # 1 second delay
            self.autosave_label.setText("Saving...")
            self.autosave_label.setStyleSheet("color: orange; padding: 2px 5px; border: 1px solid orange; border-radius: 3px;")



    def handle_editing_finished(self):
        """Called when editing is finished in any field"""
        if self.current_file:
            self.unsaved_changes = True
            self.update_stream()  # This ensures the XML is updated immediately
            self.autosave_timer.start(1000)  # 1 second delay
            self.statusBar.showMessage("Changes pending...", 1000)

    def initUI(self):
        # Set window properties
        self.setWindowTitle('SeisComP Inventory Editor')
        self.setMinimumSize(800, 600)

        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        # Add permanent autosave indicator
        self.autosave_label = QLabel("Autosave Ready")
        self.autosave_label.setStyleSheet("color: green; padding: 2px 5px; border: 1px solid green; border-radius: 3px;")
        self.statusBar.addPermanentWidget(self.autosave_label)


        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        
        # Create left panel for tree view
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add file controls with icons
        file_controls = QWidget()
        file_layout = QHBoxLayout(file_controls)
        self.load_button = QPushButton('Load XML')
        self.load_button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.save_button = QPushButton('Save XML')
        self.save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_button.setEnabled(False)
        file_layout.addWidget(self.load_button)
        file_layout.addWidget(self.save_button)
        left_layout.addWidget(file_controls)

        # Add tree widget with styling
        self.tree_widget = TreeWidgetWithKeyboardNav()
        self.tree_widget.setHeaderLabel('Inventory Structure')
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QTreeWidget::item:selected {
                background-color: #e6f3ff;
                color: black;
            }
            QTreeWidget::item:focus {
                border: 1px solid #66afe9;
                background-color: #e6f3ff;
            }
        """)

        left_layout.addWidget(self.tree_widget)
        
        # Create right panel for editing
        right_panel = QWidget()
        self.right_layout = QVBoxLayout(right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add tabs with styling
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin: 2px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QTabBar::tab:selected {
                background-color: #e6f3ff;
            }
        """)
        
        # Create tabs
        self.network_tab = QWidget()
        self.station_tab = QWidget()
        self.location_tab = QWidget()
        self.sensor_tab = QWidget()
        self.datalogger_tab = QWidget()
        self.stream_tab = QWidget()
        
        # Setup tabs
        self.setup_network_tab()
        self.setup_station_tab()
        self.setup_location_tab()
        self.setup_sensor_tab()
        self.setup_datalogger_tab()
        self.setup_stream_tab()
        
        # Add tabs to widget
        self.tab_widget.addTab(self.network_tab, "Network")
        self.tab_widget.addTab(self.station_tab, "Station")
        self.tab_widget.addTab(self.location_tab, "Location")
        self.tab_widget.addTab(self.sensor_tab, "Sensor")
        self.tab_widget.addTab(self.datalogger_tab, "Datalogger")
        self.tab_widget.addTab(self.stream_tab, "Stream")
        
        self.right_layout.addWidget(self.tab_widget)

        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        # Add splitter to layout
        layout.addWidget(splitter)

        # Connect signals
        self.load_button.clicked.connect(self.load_xml)
        self.save_button.clicked.connect(self.save_xml)
        self.tree_widget.itemClicked.connect(self.item_selected)
        
        # Create menu bar
        self.createMenuBar()

    def save_expanded_state(self):
        """Save the current expanded state of the tree"""
        expanded_items = []
        iterator = QTreeWidgetItemIterator(self.tree_widget)
        while iterator.value():
            item = iterator.value()
            if item.isExpanded():
                # Save the path to this item (e.g., "Network/Station/Location")
                path = []
                current = item
                while current:
                    path.insert(0, current.text(0))
                    current = current.parent()
                expanded_items.append('/'.join(path))
            iterator += 1
        return expanded_items

    def restore_expanded_state(self, expanded_items):
        """Restore the expanded state of the tree"""
        if not expanded_items:
            return
            
        def expand_path(item, path_parts):
            """Recursively expand items matching the path"""
            if not path_parts:
                return
            for i in range(item.childCount()):
                child = item.child(i)
                if child.text(0) == path_parts[0]:
                    if len(path_parts) == 1:
                        child.setExpanded(True)
                    else:
                        child.setExpanded(True)
                        expand_path(child, path_parts[1:])
        
        # Process each saved path
        for path in expanded_items:
            path_parts = path.split('/')
            # Start from root items
            for i in range(self.tree_widget.topLevelItemCount()):
                root_item = self.tree_widget.topLevelItem(i)
                if root_item.text(0) == path_parts[0]:
                    root_item.setExpanded(True)
                    if len(path_parts) > 1:
                        expand_path(root_item, path_parts[1:])

    def setup_network_tab(self):
        """Setup the network information tab"""
        layout = QFormLayout(self.network_tab)
        
        network_group = QGroupBox("Network Information")
        network_layout = QFormLayout()
        
        # Create validated input fields
        self.network_code = ValidationLineEdit(required=True)
        self.network_start = ValidationLineEdit()
        self.network_end = ValidationLineEdit()
        self.network_description = ValidationLineEdit()
        self.network_institutions = ValidationLineEdit()
        self.network_region = ValidationLineEdit()
        self.network_type = ValidationLineEdit()
        self.network_netClass = ValidationLineEdit()
        self.network_archive = ValidationLineEdit()
        self.network_restricted = ValidationLineEdit()
        self.network_shared = ValidationLineEdit()
        
        # Add fields to layout
        network_layout.addRow("Code:", self.network_code)
        network_layout.addRow("Start Time:", self.network_start)
        network_layout.addRow("End Time:", self.network_end)
        network_layout.addRow("Description:", self.network_description)
        network_layout.addRow("Institutions:", self.network_institutions)
        network_layout.addRow("Region:", self.network_region)
        network_layout.addRow("Type:", self.network_type)
        network_layout.addRow("Network Class:", self.network_netClass)
        network_layout.addRow("Archive:", self.network_archive)
        network_layout.addRow("Restricted:", self.network_restricted)
        network_layout.addRow("Shared:", self.network_shared)
        
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        # Add update button with styling
        self.update_network_button = QPushButton("Update Network")
        self.update_network_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.update_network_button.clicked.connect(self.update_network)
        layout.addWidget(self.update_network_button)

    def update_network(self):
        """Update the network information in the XML"""
        if hasattr(self, 'current_element'):
            try:
                # Save current expanded state
                expanded_state = self.save_expanded_state()
                
                # Update basic attributes
                if self.network_code.text():
                    self.current_element.set('code', self.network_code.text())
                
                # Update other fields
                self._update_element_text(self.current_element, 'start', self.network_start.text())
                self._update_element_text(self.current_element, 'end', self.network_end.text())
                self._update_element_text(self.current_element, 'description', self.network_description.text())
                self._update_element_text(self.current_element, 'institutions', self.network_institutions.text())
                self._update_element_text(self.current_element, 'region', self.network_region.text())
                self._update_element_text(self.current_element, 'type', self.network_type.text())
                self._update_element_text(self.current_element, 'netClass', self.network_netClass.text())
                self._update_element_text(self.current_element, 'archive', self.network_archive.text())
                self._update_element_text(self.current_element, 'restricted', self.network_restricted.text())
                self._update_element_text(self.current_element, 'shared', self.network_shared.text())
                
                # Update tree and restore expanded state
                self.populate_tree()
                self.restore_expanded_state(expanded_state)
                
                self.unsaved_changes = True
                self.statusBar.showMessage("Network updated successfully", 5000)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update network: {str(e)}")

    def setup_station_tab(self):
        layout = QFormLayout(self.station_tab)
        
        station_group = QGroupBox("Station Information")
        station_layout = QFormLayout()
        
        # Create validated input fields
        self.station_code = ValidationLineEdit(required=True)
        self.station_name = ValidationLineEdit()
        self.station_description = ValidationLineEdit()
        self.station_lat = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) and -90 <= float(x) <= 90 if x else True
        )
        self.station_lon = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) and -180 <= float(x) <= 180 if x else True
        )
        self.station_elevation = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) if x else True
        )
        
        station_layout.addRow("Code:", self.station_code)
        station_layout.addRow("Name:", self.station_name)
        station_layout.addRow("Description:", self.station_description)
        station_layout.addRow("Latitude:", self.station_lat)
        station_layout.addRow("Longitude:", self.station_lon)
        station_layout.addRow("Elevation:", self.station_elevation)
        
        station_group.setLayout(station_layout)
        layout.addWidget(station_group)
        
        # Add update button with styling
        self.update_station_button = QPushButton("Update Station")
        self.update_station_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.update_station_button.clicked.connect(self.update_station)
        layout.addWidget(self.update_station_button)

    def setup_location_tab(self):
        """Setup the sensor location information tab"""
        layout = QFormLayout(self.location_tab)
        
        location_group = QGroupBox("Sensor Location Information")
        location_layout = QFormLayout()
        
        # Create validated input fields
        self.location_code = ValidationLineEdit(required=True)
        self.location_start = ValidationLineEdit()
        self.location_end = ValidationLineEdit()
        self.location_lat = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) and -90 <= float(x) <= 90 if x else True
        )
        self.location_lon = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) and -180 <= float(x) <= 180 if x else True
        )
        self.location_elevation = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) if x else True
        )
        self.location_country = ValidationLineEdit()
        self.location_description = ValidationLineEdit()
        self.location_affiliation = ValidationLineEdit()
        
        # Add fields to layout with tooltips
        location_layout.addRow("Code:", self.location_code)
        self.location_code.setToolTip("Location code (required)")
        
        location_layout.addRow("Start Time:", self.location_start)
        self.location_start.setToolTip("Start time in ISO format (YYYY-MM-DD HH:MM:SS)")
        
        location_layout.addRow("End Time:", self.location_end)
        self.location_end.setToolTip("End time in ISO format (YYYY-MM-DD HH:MM:SS)")
        
        location_layout.addRow("Latitude (°):", self.location_lat)
        self.location_lat.setToolTip("Latitude in decimal degrees (-90 to 90)")
        
        location_layout.addRow("Longitude (°):", self.location_lon)
        self.location_lon.setToolTip("Longitude in decimal degrees (-180 to 180)")
        
        location_layout.addRow("Elevation (m):", self.location_elevation)
        self.location_elevation.setToolTip("Elevation in meters above sea level")
        
        location_layout.addRow("Country:", self.location_country)
        location_layout.addRow("Description:", self.location_description)
        location_layout.addRow("Affiliation:", self.location_affiliation)
        
        location_group.setLayout(location_layout)
        layout.addWidget(location_group)
        
        # Add update button with styling
        self.update_location_button = QPushButton("Update Location")
        self.update_location_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.update_location_button.clicked.connect(self.update_location)
        layout.addWidget(self.update_location_button)

    def update_location(self):
        """Update the sensor location information in the XML"""
        if hasattr(self, 'current_element'):
            try:
                # Save current expanded state
                expanded_state = self.save_expanded_state()
                
                # Update basic attributes
                if self.location_code.text():
                    self.current_element.set('code', self.location_code.text())
                
                # Update other fields
                fields_to_update = {
                    'start': self.location_start.text(),
                    'end': self.location_end.text(),
                    'latitude': self.location_lat.text(),
                    'longitude': self.location_lon.text(),
                    'elevation': self.location_elevation.text(),
                    'country': self.location_country.text(),
                    'description': self.location_description.text(),
                    'affiliation': self.location_affiliation.text()
                }
                
                for field, value in fields_to_update.items():
                    self._update_element_text(self.current_element, field, value)
                
                # Update tree and restore expanded state
                self.populate_tree()
                self.restore_expanded_state(expanded_state)
                
                self.unsaved_changes = True
                self.statusBar.showMessage("Location updated successfully", 5000)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update location: {str(e)}")

    def setup_sensor_tab(self):
        layout = QFormLayout(self.sensor_tab)
        
        sensor_group = QGroupBox("Sensor Information")
        sensor_layout = QFormLayout()
        
        self.sensor_name = ValidationLineEdit()
        self.sensor_type = ValidationLineEdit()
        self.sensor_model = ValidationLineEdit()
        self.sensor_manufacturer = ValidationLineEdit()
        self.sensor_serial = ValidationLineEdit()
        
        sensor_layout.addRow("Name:", self.sensor_name)
        sensor_layout.addRow("Type:", self.sensor_type)
        sensor_layout.addRow("Model:", self.sensor_model)
        sensor_layout.addRow("Manufacturer:", self.sensor_manufacturer)
        sensor_layout.addRow("Serial Number:", self.sensor_serial)
        
        sensor_group.setLayout(sensor_layout)
        layout.addWidget(sensor_group)
        
        # Add update button
        self.update_sensor_button = QPushButton("Update Sensor")
        self.update_sensor_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.update_sensor_button.clicked.connect(self.update_sensor)
        layout.addWidget(self.update_sensor_button)

    def setup_datalogger_tab(self):
        layout = QFormLayout(self.datalogger_tab)
        
        datalogger_group = QGroupBox("Datalogger Information")
        datalogger_layout = QFormLayout()
        
        self.datalogger_name = ValidationLineEdit()
        self.datalogger_type = ValidationLineEdit()
        self.datalogger_model = ValidationLineEdit()
        self.datalogger_manufacturer = ValidationLineEdit()
        self.datalogger_serial = ValidationLineEdit()
        
        datalogger_layout.addRow("Name:", self.datalogger_name)
        datalogger_layout.addRow("Type:", self.datalogger_type)
        datalogger_layout.addRow("Model:", self.datalogger_model)
        datalogger_layout.addRow("Manufacturer:", self.datalogger_manufacturer)
        datalogger_layout.addRow("Serial Number:", self.datalogger_serial)
        
        datalogger_group.setLayout(datalogger_layout)
        layout.addWidget(datalogger_group)
        
        # Add update button
        self.update_datalogger_button = QPushButton("Update Datalogger")
        self.update_datalogger_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.update_datalogger_button.clicked.connect(self.update_datalogger)
        layout.addWidget(self.update_datalogger_button)

    def setup_stream_tab(self):
        layout = QFormLayout(self.stream_tab)
        
        stream_group = QGroupBox("Stream/Channel Information")
        stream_layout = QFormLayout()
        
        # Create validated input fields with proper parent
        self.stream_code = ValidationLineEdit(required=True, parent=self)
        self.stream_start = ValidationLineEdit(parent=self)
        self.stream_end = ValidationLineEdit(parent=self)
        self.stream_depth = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) if x else True,
            parent=self
        )
        self.stream_azimuth = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) and 0 <= float(x) <= 360 if x else True,
            parent=self
        )
        self.stream_dip = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) and -90 <= float(x) <= 90 if x else True,
            parent=self
        )
        self.stream_gain = ValidationLineEdit(
            validator=lambda x: re.match(r'^-?\d*\.?\d*$', x) if x else True,
            parent=self
        )
        self.stream_sampleRate = ValidationLineEdit(
            validator=lambda x: re.match(r'^\d*\.?\d*$', x) if x else True,
            parent=self
        )
        self.stream_gainFrequency = ValidationLineEdit(
            validator=lambda x: re.match(r'^\d*\.?\d*$', x) if x else True,
            parent=self
        )
        self.stream_gainUnit = ValidationLineEdit(parent=self)
        self.stream_datalogger_serialnumber = ValidationLineEdit(parent=self)
        self.stream_sensor_serialnumber = ValidationLineEdit(parent=self)
        self.stream_flags = ValidationLineEdit(parent=self)
        
        # Add fields to layout
        stream_layout.addRow("Code:", self.stream_code)
        stream_layout.addRow("Start Time:", self.stream_start)
        stream_layout.addRow("End Time:", self.stream_end)
        stream_layout.addRow("Depth (m):", self.stream_depth)
        stream_layout.addRow("Azimuth (°):", self.stream_azimuth)
        stream_layout.addRow("Dip (°):", self.stream_dip)
        stream_layout.addRow("Gain:", self.stream_gain)
        stream_layout.addRow("Sample Rate (Hz):", self.stream_sampleRate)
        stream_layout.addRow("Gain Frequency (Hz):", self.stream_gainFrequency)
        stream_layout.addRow("Gain Unit:", self.stream_gainUnit)
        stream_layout.addRow("Datalogger S/N:", self.stream_datalogger_serialnumber)
        stream_layout.addRow("Sensor S/N:", self.stream_sensor_serialnumber)
        stream_layout.addRow("Flags:", self.stream_flags)
        
        stream_group.setLayout(stream_layout)
        layout.addWidget(stream_group)
        
        # Add update button
        self.update_stream_button = QPushButton("Update Stream")
        self.update_stream_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.update_stream_button.clicked.connect(self.update_stream)
        layout.addWidget(self.update_stream_button)

    def createMenuBar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        open_action = QAction('Open', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.load_xml)
        file_menu.addAction(open_action)
        
        save_action = QAction('Save', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_xml)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu('Edit')

        # Add Help menu with keyboard shortcuts reference
        help_menu = self.menuBar().addMenu('Help')
        shortcuts_action = QAction('Keyboard Shortcuts', self)
        shortcuts_action.triggered.connect(self.show_shortcuts_help)
        help_menu.addAction(shortcuts_action)

        expand_all_action = QAction('Expand All', self)
        expand_all_action.triggered.connect(self.tree_widget.expandAll)
        edit_menu.addAction(expand_all_action)
        
        collapse_all_action = QAction('Collapse All', self)
        collapse_all_action.triggered.connect(self.tree_widget.collapseAll)
        edit_menu.addAction(collapse_all_action)

    def show_shortcuts_help(self):
        """Show a dialog with keyboard shortcuts reference"""
        shortcuts_text = """
Keyboard Shortcuts:
------------------
Navigation:
↑/↓: Move between items
←/→: Collapse/Expand items
Enter: Select item
Home: Go to first item
End: Go to last item
Tab: Move between fields

Global:
Ctrl+O: Open file
Ctrl+S: Save file
Ctrl+Q: Quit
F5: Expand all
F6: Collapse all
"""

    def loadSettings(self):
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        windowState = self.settings.value('windowState')
        if windowState:
            self.restoreState(windowState)
        lastDir = self.settings.value('lastDirectory')
        if lastDir:
            self.last_directory = lastDir

    def closeEvent(self, event):
        """Handle application close event"""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, 'Save Changes?',
                'There are unsaved changes. Do you want to save before closing?',
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Save:
                self.save_xml()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
                
        # Save application settings
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('windowState', self.saveState())
        if hasattr(self, 'last_directory'):
            self.settings.setValue('lastDirectory', self.last_directory)
        
        event.accept()

    def load_xml(self):
        """Load XML file with error handling and validation"""
        try:
            start_dir = getattr(self, 'last_directory', '')
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load SeisComP Inventory",
                start_dir, "XML files (*.xml)"
            )
            
            if filename:
                self.last_directory = str(Path(filename).parent)
                tree = ET.parse(filename)
                root = tree.getroot()
                
                # Validate XML structure
                if not self._validate_xml_structure(root):
                    QMessageBox.warning(
                        self, "Invalid File",
                        "The selected file does not appear to be a valid SeisComP inventory file."
                    )
                    return
                
                self.current_file = filename
                self.tree = tree
                self.root = root
                self.populate_tree()
                self.save_button.setEnabled(True)
                self.statusBar.showMessage(f"Loaded: {filename}", 5000)
                
        except ET.ParseError as e:
            QMessageBox.critical(
                self, "XML Parse Error",
                f"Failed to parse XML file:\n{str(e)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"An unexpected error occurred:\n{str(e)}"
            )

    def _validate_xml_structure(self, root):
        """Validate basic SeisComP XML structure"""
        if root.tag != f'{{{self.ns["sc3"]}}}seiscomp':
            return False
        inventory = root.find('sc3:Inventory', self.ns)
        return inventory is not None

    def register_namespaces(self):
        """Register the namespace to avoid sc3: prefix"""
        ET.register_namespace('', self.ns['sc3'])
        ET.register_namespace('xmlns', self.ns['sc3'])


    def save_xml(self):
        """Save XML while preserving exact original formatting"""
        if self.current_file and self.tree:
            try:
                # Create backup
                current_path = Path(self.current_file)
                backup_path = current_path.with_suffix('.xml.bak')
                
                if current_path.exists():
                    current_path.rename(backup_path)
                
                # Read the original file content
                with open(backup_path, 'r', encoding='UTF-8') as f:
                    content = f.read()
                
                # Apply each tracked change
                if hasattr(self, 'modified_elements'):
                    for element_id, changes in self.modified_elements.items():
                        # Find the element in the content
                        element_start = content.find(f'publicID="{element_id}"')
                        if element_start != -1:
                            # Find element boundaries
                            block_start = content.rfind('<', 0, element_start)
                            block_end = content.find('</stream>', element_start)
                            if block_end == -1:
                                block_end = content.find('>', element_start) + 1
                            
                            # Get the element's content
                            element_content = content[block_start:block_end]
                            
                            # Get proper indentation
                            lines = element_content.split('\n')
                            if len(lines) > 1:
                                # Get indentation from the second line
                                indent_match = re.match(r'^(\s+)', lines[1])
                                child_indent = indent_match.group(1) if indent_match else '            '
                            else:
                                child_indent = '            '
                            
                            modified_content = element_content
                            
                            # Apply each change
                            for field, new_value in changes.items():
                                # Look for existing field
                                field_tag = f"<{field}>"
                                field_start = modified_content.find(field_tag)
                                
                                if field_start != -1:
                                    # Update existing field
                                    field_end = modified_content.find(f"</{field}>", field_start)
                                    if field_end != -1:
                                        field_content = modified_content[field_start:field_end + len(f"</{field}>")]
                                        new_field_content = f"<{field}>{new_value}</{field}>"
                                        modified_content = modified_content.replace(
                                            field_content,
                                            new_field_content
                                        )
                                else:
                                    # Add new field with proper indentation
                                    # Find the last complete element
                                    last_elem_end = -1
                                    for line in reversed(modified_content.split('\n')):
                                        if line.strip().endswith('</shared>'):
                                            last_elem_end = modified_content.rfind('</shared>')
                                            break
                                        if line.strip().endswith('/>'):
                                            last_elem_end = modified_content.rfind('/>')
                                            break
                                        if line.strip().endswith('>'):
                                            close_tag = line.strip()[2:-1]  # Get tag name from </tag>
                                            if close_tag and modified_content.rfind(f'</{close_tag}>') != -1:
                                                last_elem_end = modified_content.rfind(f'</{close_tag}>')
                                                break
                                    
                                    if last_elem_end != -1:
                                        # Insert after the last complete element
                                        new_field_content = f"\n{child_indent}<{field}>{new_value}</{field}>"
                                        end_tag_pos = modified_content.find('>', last_elem_end) + 1
                                        modified_content = (
                                            modified_content[:end_tag_pos] +
                                            new_field_content +
                                            modified_content[end_tag_pos:]
                                        )
                            
                            # Replace the original content with modified content
                            content = content[:block_start] + modified_content + content[block_end:]
                
                # Write the modified content back to file
                with open(str(current_path), 'w', encoding='UTF-8') as f:
                    f.write(content)
                
                # Clear tracking
                self.modified_elements = {}
                self.unsaved_changes = False
                
                self.statusBar.showMessage("File saved successfully", 5000)
                self.autosave_label.setText("Changes Saved")
                self.autosave_label.setStyleSheet(
                    "color: green; padding: 2px 5px; border: 1px solid green; border-radius: 3px;"
                )
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save XML: {str(e)}")
                if backup_path.exists():
                    backup_path.rename(current_path)
                self.autosave_label.setText("Save Failed")
                self.autosave_label.setStyleSheet(
                    "color: red; padding: 2px 5px; border: 1px solid red; border-radius: 3px;"
                )

                    
    def populate_tree(self):
        """Populate tree with sorted channels"""
        self.tree_widget.clear()
        inventory = self.root.find('sc3:Inventory', self.ns)
        if inventory is None:
            return

        # Add networks
        for network in inventory.findall('.//sc3:network', self.ns):
            network_item = QTreeWidgetItem(self.tree_widget)
            network_item.setText(0, f"Network: {network.get('code', '')}")
            network_item.setData(0, Qt.UserRole, ('network', network))
            
            # Add stations
            for station in network.findall('.//sc3:station', self.ns):
                station_item = QTreeWidgetItem(network_item)
                station_item.setText(0, f"Station: {station.get('code', '')}")
                station_item.setData(0, Qt.UserRole, ('station', station))
                
                # Add sensor locations
                for location in station.findall('.//sc3:sensorLocation', self.ns):
                    location_item = QTreeWidgetItem(station_item)
                    location_item.setText(0, f"Location: {location.get('code', '')}")
                    location_item.setData(0, Qt.UserRole, ('location', location))

                    # Get all streams and sort them - Fixed line here
                    streams = location.findall('sc3:stream', self.ns)
                    sorted_streams = self.sort_channels(streams)  # Added self.

                    # Add sorted streams under location
                    for stream in sorted_streams:
                        stream_item = QTreeWidgetItem(location_item)
                        stream_item.setText(0, f"Stream: {stream.get('code', '')}")
                        stream_item.setData(0, Qt.UserRole, ('stream', stream))

        # Add sensors and dataloggers sections
        sensors = inventory.findall('.//sc3:sensor', self.ns)
        if sensors:
            sensors_item = QTreeWidgetItem(self.tree_widget)
            sensors_item.setText(0, "Sensors")
            for sensor in sensors:
                sensor_item = QTreeWidgetItem(sensors_item)
                sensor_item.setText(0, f"Sensor: {sensor.get('name', '')}")
                sensor_item.setData(0, Qt.UserRole, ('sensor', sensor))

        dataloggers = inventory.findall('.//sc3:datalogger', self.ns)
        if dataloggers:
            dataloggers_item = QTreeWidgetItem(self.tree_widget)
            dataloggers_item.setText(0, "Dataloggers")
            for datalogger in dataloggers:
                datalogger_item = QTreeWidgetItem(dataloggers_item)
                datalogger_item.setText(0, f"Datalogger: {datalogger.get('name', '')}")
                datalogger_item.setData(0, Qt.UserRole, ('datalogger', datalogger))

    def _get_element_text(self, element, tag, default=''):
        """Helper method to get element text with namespace and default value"""
        elem = element.find(f'sc3:{tag}', self.ns)
        return elem.text if elem is not None else default

    def sort_channels(self, channels):
        """
        Sort channels according to seismological convention:
        1. First by band and instrument code (B, H, etc.)
        2. Then by orientation (E/1, N/2, Z) or (1, 2, Z)
        
        Handles both cardinal (N,E,Z) and numerical (1,2,Z) orientation codes.
        
        Args:
            channels: List of stream elements from XML
        Returns:
            Sorted list of stream elements
        """
        def get_sort_key(channel):
            # Get channel code (e.g., 'BHZ', 'HH1', etc.)
            code = channel.get('code', '')
            if not code or len(code) < 3:
                return ('', '', 999)  # Handle invalid codes
                
            # Split into components (e.g., 'B', 'H', 'Z' or 'B', 'H', '1')
            band_code = code[0]  # B, H, etc.
            instrument_code = code[1]  # H, N, etc.
            orientation = code[2]  # Z, N, E, 1, 2
            
            # Custom orientation order:
            # E/1 should come first
            # N/2 should come second
            # Z should come last
            # Any other characters come after Z
            orientation_order = {
                'E': 0, '1': 0,  # E and 1 are equivalent
                'N': 1, '2': 1,  # N and 2 are equivalent
                'Z': 2,          # Z always comes last
            }
            orientation_value = orientation_order.get(orientation, 3)
            
            # For debugging
            # print(f"Code: {code} -> Band: {band_code}, Inst: {instrument_code}, " \
            #       f"Orient: {orientation} -> {orientation_value}")
            
            return (band_code, instrument_code, orientation_value)
        
        return sorted(channels, key=get_sort_key)

    def _update_element_text(self, element, tag, value, old_value=None):
        """Helper method to update element text with namespace and change tracking"""
        elem = element.find(f'sc3:{tag}', self.ns)
        
        if elem is None:
            if value:  # Only create new elements for non-empty values
                elem = ET.SubElement(element, f'{{{self.ns["sc3"]}}}{tag}')
                elem.text = value
                self.unsaved_changes = True
        else:
            current_value = elem.text if elem.text is not None else ""
            if value != current_value:  # Only update if value has changed
                if value:
                    elem.text = value
                else:
                    element.remove(elem)
                self.unsaved_changes = True


    def update_station(self):
        if hasattr(self, 'current_element'):
            try:
                # Only set attributes if they have non-empty values
                if self.station_code.text():
                    self.current_element.set('code', self.station_code.text())
                if self.station_name.text():
                    self.current_element.set('name', self.station_name.text())
                elif 'name' in self.current_element.attrib:
                    del self.current_element.attrib['name']  # Remove empty name attribute
                    
                # Update element texts
                self._update_element_text(self.current_element, 'description', self.station_description.text())
                self._update_element_text(self.current_element, 'latitude', self.station_lat.text())
                self._update_element_text(self.current_element, 'longitude', self.station_lon.text())
                self._update_element_text(self.current_element, 'elevation', self.station_elevation.text())
                
                self.populate_tree()
                self.unsaved_changes = True
                self.statusBar.showMessage("Station updated successfully", 5000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update station: {str(e)}")


    def update_sensor(self):
        if hasattr(self, 'current_element'):
            try:
                self.current_element.set('name', self.sensor_name.text())
                self._update_element_text(self.current_element, 'type', self.sensor_type.text())
                self._update_element_text(self.current_element, 'model', self.sensor_model.text())
                self._update_element_text(self.current_element, 'manufacturer', self.sensor_manufacturer.text())
                self._update_element_text(self.current_element, 'serialNumber', self.sensor_serial.text())
                self.populate_tree()
                self.unsaved_changes = True
                self.statusBar.showMessage("Sensor updated successfully", 5000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update sensor: {str(e)}")

    def update_datalogger(self):
        if hasattr(self, 'current_element'):
            try:
                self.current_element.set('name', self.datalogger_name.text())
                self._update_element_text(self.current_element, 'type', self.datalogger_type.text())
                self._update_element_text(self.current_element, 'model', self.datalogger_model.text())
                self._update_element_text(self.current_element, 'manufacturer', self.datalogger_manufacturer.text())
                self._update_element_text(self.current_element, 'serialNumber', self.datalogger_serial.text())
                self.populate_tree()
                self.unsaved_changes = True
                self.statusBar.showMessage("Datalogger updated successfully", 5000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update datalogger: {str(e)}")

    def update_stream(self):
        """Update the XML element with values from the stream fields"""
        if hasattr(self, 'current_element'):
            try:
                # Save current expanded state
                expanded_state = self.save_expanded_state()
                
                # Initialize modified elements tracking if not exists
                if not hasattr(self, 'modified_elements'):
                    self.modified_elements = {}
                
                # Track current values and changes
                element_id = self.current_element.get('publicID', '')
                current_values = {
                    'depth': self._get_element_text(self.current_element, 'depth'),
                    'azimuth': self._get_element_text(self.current_element, 'azimuth'),
                    'dip': self._get_element_text(self.current_element, 'dip'),
                    'gain': self._get_element_text(self.current_element, 'gain'),
                    'gainFrequency': self._get_element_text(self.current_element, 'gainFrequency'),
                    'gainUnit': self._get_element_text(self.current_element, 'gainUnit'),
                }
                
                # Process each field
                fields_to_update = {
                    'depth': self.stream_depth.text(),
                    'azimuth': self.stream_azimuth.text(),
                    'dip': self.stream_dip.text(),
                    'gain': self.stream_gain.text(),
                    'gainFrequency': self.stream_gainFrequency.text(),
                    'gainUnit': self.stream_gainUnit.text(),
                }
                
                # Store changes for saving
                changes = {}
                changes_made = False
                
                for field, new_value in fields_to_update.items():
                    current = current_values.get(field, '')
                    if new_value != current:
                        tag = f"sc3:{field}"
                        elem = self.current_element.find(tag, self.ns)
                        
                        if elem is None and new_value:
                            # Create new element if it doesn't exist
                            elem = ET.SubElement(self.current_element, f'{{{self.ns["sc3"]}}}{field}')
                            elem.text = new_value
                            changes_made = True
                            changes[field] = new_value
                        elif elem is not None:
                            if new_value:
                                # Update existing element
                                elem.text = new_value
                                changes_made = True
                                changes[field] = new_value
                            else:
                                # Remove element if value is empty
                                self.current_element.remove(elem)
                                changes_made = True
                                changes[field] = ''
                
                if changes_made:
                    # Store changes for saving
                    if element_id:
                        self.modified_elements[element_id] = changes
                    self.unsaved_changes = True
                    
                    # Update tree while preserving expanded state
                    self.populate_tree()
                    self.restore_expanded_state(expanded_state)
                    
                    self.statusBar.showMessage("Stream updated successfully", 5000)
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update stream: {str(e)}")
                self.statusBar.showMessage(f"Update failed: {str(e)}", 5000)

    def item_selected(self, item):
        if not item:
            return
            
        item_type, element = item.data(0, Qt.UserRole)
        self.current_element = element
        
        if item_type == 'network':  # Add this block
            self.tab_widget.setCurrentWidget(self.network_tab)
            self.populate_network_fields(element)
        elif item_type == 'station':
            self.tab_widget.setCurrentWidget(self.station_tab)
            self.populate_station_fields(element)
        elif item_type == 'location':
            self.tab_widget.setCurrentWidget(self.stream_tab)
            self.populate_stream_fields(element)
        elif item_type == 'sensor':
            self.tab_widget.setCurrentWidget(self.sensor_tab)
            self.populate_sensor_fields(element)
        elif item_type == 'datalogger':
            self.tab_widget.setCurrentWidget(self.datalogger_tab)
            self.populate_datalogger_fields(element)
        elif item_type == 'stream':
            self.tab_widget.setCurrentWidget(self.stream_tab)
            self.populate_stream_fields(element)

    def populate_network_fields(self, network):
        """Populate the network fields with data from the XML element"""
        try:
            # Basic attributes
            self.network_code.setText(network.get('code', ''))
            
            # Element fields
            self.network_start.setText(self._get_element_text(network, 'start'))
            self.network_end.setText(self._get_element_text(network, 'end'))
            self.network_description.setText(self._get_element_text(network, 'description'))
            self.network_institutions.setText(self._get_element_text(network, 'institutions'))
            self.network_region.setText(self._get_element_text(network, 'region'))
            self.network_type.setText(self._get_element_text(network, 'type'))
            self.network_netClass.setText(self._get_element_text(network, 'netClass'))
            self.network_archive.setText(self._get_element_text(network, 'archive'))
            self.network_restricted.setText(self._get_element_text(network, 'restricted'))
            self.network_shared.setText(self._get_element_text(network, 'shared'))
            
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error populating network fields: {str(e)}")

    def populate_station_fields(self, station):
        self.station_code.setText(station.get('code', ''))
        self.station_name.setText(station.get('name', ''))
        self.station_description.setText(self._get_element_text(station, 'description'))
        self.station_lat.setText(self._get_element_text(station, 'latitude'))
        self.station_lon.setText(self._get_element_text(station, 'longitude'))
        self.station_elevation.setText(self._get_element_text(station, 'elevation'))

    def populate_location_fields(self, location):
        """Populate the location fields with data from the XML element"""
        try:
            # Basic attributes
            self.location_code.setText(location.get('code', ''))
            
            # Element fields
            self.location_start.setText(self._get_element_text(location, 'start'))
            self.location_end.setText(self._get_element_text(location, 'end'))
            self.location_lat.setText(self._get_element_text(location, 'latitude'))
            self.location_lon.setText(self._get_element_text(location, 'longitude'))
            self.location_elevation.setText(self._get_element_text(location, 'elevation'))
            self.location_country.setText(self._get_element_text(location, 'country'))
            self.location_description.setText(self._get_element_text(location, 'description'))
            self.location_affiliation.setText(self._get_element_text(location, 'affiliation'))
            
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error populating location fields: {str(e)}")

    def populate_sensor_fields(self, sensor):
        self.sensor_name.setText(sensor.get('name', ''))
        self.sensor_type.setText(self._get_element_text(sensor, 'type'))
        self.sensor_model.setText(self._get_element_text(sensor, 'model'))
        self.sensor_manufacturer.setText(self._get_element_text(sensor, 'manufacturer'))
        self.sensor_serial.setText(self._get_element_text(sensor, 'serialNumber'))

    def populate_datalogger_fields(self, datalogger):
        self.datalogger_name.setText(datalogger.get('name', ''))
        self.datalogger_type.setText(self._get_element_text(datalogger, 'type'))
        self.datalogger_model.setText(self._get_element_text(datalogger, 'model'))
        self.datalogger_manufacturer.setText(self._get_element_text(datalogger, 'manufacturer'))
        self.datalogger_serial.setText(self._get_element_text(datalogger, 'serialNumber'))

    def populate_stream_fields(self, stream):
        """Populate all stream fields from the XML element"""
        try:
            # Basic attributes
            self.stream_code.setText(stream.get('code', ''))
            
            # Time fields
            self.stream_start.setText(self._get_element_text(stream, 'start'))
            self.stream_end.setText(self._get_element_text(stream, 'end'))
            
            # Position fields
            self.stream_depth.setText(self._get_element_text(stream, 'depth'))
            self.stream_azimuth.setText(self._get_element_text(stream, 'azimuth'))
            self.stream_dip.setText(self._get_element_text(stream, 'dip'))
            
            # Gain and sampling fields
            self.stream_gain.setText(self._get_element_text(stream, 'gain'))
            
            # Calculate sample rate from numerator/denominator
            numerator = self._get_element_text(stream, 'sampleRateNumerator', '0')
            denominator = self._get_element_text(stream, 'sampleRateDenominator', '1')
            try:
                if numerator and denominator and float(denominator) != 0:
                    sample_rate = float(numerator) / float(denominator)
                    self.stream_sampleRate.setText(f"{sample_rate:.1f}")
                else:
                    self.stream_sampleRate.setText('')
            except (ValueError, ZeroDivisionError):
                self.stream_sampleRate.setText('')
            
            self.stream_gainFrequency.setText(self._get_element_text(stream, 'gainFrequency'))
            self.stream_gainUnit.setText(self._get_element_text(stream, 'gainUnit'))
            
            # Additional fields
            self.stream_datalogger_serialnumber.setText(self._get_element_text(stream, 'dataloggerSerialNumber'))
            self.stream_sensor_serialnumber.setText(self._get_element_text(stream, 'sensorSerialNumber'))
            self.stream_flags.setText(self._get_element_text(stream, 'flags'))
            
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error populating stream fields: {str(e)}")

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
    app.setPalette(palette)
    editor = SeisCompInventoryEditor()
    editor.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()