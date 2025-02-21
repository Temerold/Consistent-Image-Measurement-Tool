import sys
from pathlib import Path
from typing import Callable

import yaml
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenuBar, QTextEdit


class MainWindow(QMainWindow):
    def __init__(self, config, developer_config):
        self.config = config
        self.developer_config = developer_config
        self.script_dir = Path(__file__).parent

        super().__init__()
        self.set_initial_window_position()
        self.setWindowTitle("Consistent Image Measurement Tool")
        self.setWindowIcon(
            QIcon(str(Path(self.script_dir / self.developer_config["gui"]["icon"])))
        )
        self.create_gui()

    def create_gui(self):
        self.text_edit = QTextEdit(self)
        self.setCentralWidget(self.text_edit)

        self.create_menu_item_bar()

    def new_project(self):
        print("New project")

    def open_project(self):
        print("Open project")

    def save_project(self):
        print("Save project")

    def save_project_as_image(self):
        print("Save project as image")

    def settings(self):
        print("Settings")

    def about(self):
        print("About")

    def set_initial_window_position(self):
        width, height = self.config["gui"]["initial_size"]
        initial_x, initial_y = self.config["gui"]["initial_position"]
        screen = app.primaryScreen().availableGeometry()

        if config["gui"]["maximized"]:
            self.showMaximized()
            return

        if config["gui"]["full_screen"]:
            self.showFullScreen()
            return

        width = round(width if width > 1 else width * screen.width()) or 1
        height = round(height if height > 1 else height * screen.height()) or 1

        if initial_x == -1:
            initial_x = (screen.width() - width) // 2
        else:
            initial_x *= screen.width()
        if initial_y == -1:
            initial_y = (screen.height() - height) // 2
        else:
            initial_y *= screen.height()

        self.setGeometry(initial_x, initial_y, width, height)

    def create_menu_item_bar(self) -> QAction | QMenuBar:
        def create_menu_item(menu_name: str, menu_item: Callable | dict, parent_menu):
            if callable(menu_item):
                new_menu_item = QAction(menu_name, self)
                new_menu_item.triggered.connect(menu_item)
                parent_menu.addAction(new_menu_item)
            elif isinstance(menu_item, dict):
                parent_menu = parent_menu.addMenu(menu_name)
                for parent, child in menu_item.items():
                    new_menu_item = create_menu_item(parent, child, parent_menu)
            else:
                raise ValueError("Menu item must be a callable or a dictionary or.")
            return new_menu_item

        menu = {
            "File": {
                "New project": self.new_project,
                "Open project": self.open_project,
                "Save project": self.save_project,
                "Save project as image": self.save_project_as_image,
            },
            "Settings": self.settings,
            "Help": {"About": self.about},
        }

        menu_bar = self.menuBar()
        for parent, child in menu.items():
            create_menu_item(parent, child, menu_bar)


def load_config(file_path):
    script_dir = Path(__file__).parent
    file_path = script_dir / file_path
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


if __name__ == "__main__":
    config = load_config("config.yaml")
    developer_config = load_config("developer_config.yaml")
    app = QApplication(sys.argv)
    app.setStyle(developer_config["gui"]["style"])
    main_window = MainWindow(config, developer_config)
    main_window.show()
    sys.exit(app.exec())
