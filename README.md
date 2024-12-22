# SeisComP Inventory Editor GUI

A Python-based graphical user interface tool for editing SeisComP inventory XML files. This tool allows users to view and modify station metadata, sensor configurations, datalogger settings, and stream parameters in a user-friendly interface.

## Features

- Load and edit SeisComP inventory XML files
- Tree-based visualization of the inventory structure
- Edit station information (code, name, description, coordinates)
- Modify sensor and datalogger configurations
- Update stream parameters (depth, gain, sample rate, etc.)
- Validation of input fields
- Auto-save functionality
- Maintains original XML formatting when saving changes

## Requirements

- Python 3.x
- PyQt5
- xml.etree.ElementTree

## Installation

1. Clone the repository:
```bash
git clone https://github.com/comoglu/seiscomp-inventory-editor-gui.py.git
```

2. Install the required dependencies:
```bash
pip install PyQt5
```
## Screenshot
![Interface](https://github.com/user-attachments/assets/302f709c-b2a2-436b-b646-350c91575886)

## Usage

Run the application:
```bash
python seiscomp-inventory-editor-gui.py
```

### Basic Operations

1. **Loading an Inventory File**
   - Click the "Load XML" button or use File → Open
   - Select your SeisComP inventory XML file

2. **Navigating the Inventory**
   - Use the tree view on the left to browse through networks, stations, and channels
   - Click on any item to view and edit its properties

3. **Editing Components**
   - Station: Edit station code, name, description, and coordinates
   - Sensor: Modify sensor configurations and parameters
   - Datalogger: Update datalogger settings
   - Stream: Edit stream parameters including depth, gain, and sample rate

4. **Saving Changes**
   - Click "Save XML" or use File → Save to save your changes
   - The tool preserves the original XML formatting
   - A backup of the original file is created before saving

### Features Details

- **Validation**: Input fields are validated in real-time with visual feedback
- **Auto-save**: Changes are automatically saved after modifications
- **Backup**: Original files are backed up before saving changes
- **Tree State Preservation**: The tree view maintains its expanded state during updates

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Author

Mustafa Comoglu

## Support

For issues, questions, or feature requests, please [create an issue](https://github.com/comoglu/seiscomp-inventory-editor-gui.py/issues) on GitHub.
