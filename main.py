import json
import sys
from pathlib import Path
from typing import Callable

import yaml
from PyQt6.QtCore import QBuffer, QByteArray, QFileInfo, QIODevice, QSize, Qt
from PyQt6.QtGui import QAction, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
)


def get_element(object, index, fallback):
    try:
        return object[index]
    except IndexError:
        return fallback


class Project:
    def __init__(self):
        self.unscaled_pixmap = QPixmap()
        self.measurements = []

    def image_to_base_64(self, image: QImage):
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")  # TODO: Save it as its original file format
        return byte_array.toBase64().data()

    def save(self, filepath) -> None:
        image = self.unscaled_pixmap.toImage()
        data = {
            "image": self.image_to_base_64(image).decode("utf-8"),
            "measurements": self.measurements,
        }
        with open(filepath, "w") as file:
            json.dump(data, file)


class MainWindow(QMainWindow):
    def __init__(self, config: dict, developer_config: dict):
        self.config: dict = config
        self.developer_config: dict = developer_config
        self.script_dir: Path = Path(__file__).parent
        self.application_title: str = self.developer_config["gui"]["title"]
        self.application_icon: QIcon = QIcon(
            str(self.script_dir / self.developer_config["gui"]["icon"])
        )
        self.project = Project()

        super().__init__()
        self.setWindowTitle(self.application_title)
        self.setWindowIcon(self.application_icon)
        self.set_initial_window_position()
        self.create_gui()

    def create_gui(self):
        self.image_viewer = QLabel(self)
        self.image_viewer.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.setCentralWidget(self.image_viewer)

        self.create_menu_item_bar()
        self.create_tool_bar()

    def resizeEvent(self, _):
        unscaled_pixmap = self.project.unscaled_pixmap
        if unscaled_pixmap.isNull():
            return

        # According to my own testing, images whose largest dimension is 64 or less look
        # better when `Qt.TransformationMode.FastTransformation` is used, while larger
        # images look better when `Qt.TransformationMode.SmoothTransformation` is used.
        # TODO: Consider using a more sophisticated algorithm to determine the best
        # transformation mode. Nearest neighbor interpolation might be better for pixel
        # accuaracy, which is important for the measurements.
        largest_size = max(unscaled_pixmap.width(), unscaled_pixmap.height())
        if largest_size > 64:
            transformation_mode = Qt.TransformationMode.SmoothTransformation
        else:
            transformation_mode = Qt.TransformationMode.FastTransformation

        scaled_image = unscaled_pixmap.scaled(
            self.image_viewer.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            transformation_mode,
        )
        self.image_viewer.setPixmap(scaled_image)

    def create_tool_bar(self) -> QMenuBar:
        def create_tool_bar_button(
            tool_bar: str,
            icon_path: str,
            hover_text: str,
            status_text: str,
            action: Callable,
            checkable: bool = False,
        ) -> QAction:
            icon_path = str(self.script_dir / icon_path)
            # Using `QIcon(icon_path)` doesn't scale the icon, so we pass a `QPixmap` to
            # `QIcon` instead
            icon_pixmap = QPixmap(icon_path)
            icon_pixmap = icon_pixmap.scaled(
                QSize(icon_width, icon_width), Qt.AspectRatioMode.KeepAspectRatio
            )
            icon = QIcon(icon_pixmap)
            button = QAction(icon, hover_text, self)

            action_ = lambda *a: action(
                *a, button, icon_path, hover_text, status_text, checkable
            )
            button.triggered.connect(action_)
            button.setCheckable(checkable)
            tool_bar.addAction(button)

            return button

        self.tool_bar = QToolBar(self)
        icon_width = self.developer_config["gui"]["tool_bar"]["icon_width"]
        self.tool_bar.setIconSize(QSize(icon_width, icon_width))
        self.addToolBar(self.tool_bar)

        self.status_bar = self.statusBar()
        self.current_action = QLabel()
        self.current_sub_action = QLabel()
        self.status_bar.addWidget(self.current_action)
        self.status_bar.addWidget(self.current_sub_action)

        tool_bar_icons = self.developer_config["gui"]["tool_bar"]["icons"]
        self.tool_bar_buttons = [
            {
                "icon_path": tool_bar_icons["draw_line"],
                "hover_text": "Draw line",
                "status_text": "Drawing line",
                "action": self.draw_line,
                "checkable": True,
            }
        ]
        for tool_bar_button in self.tool_bar_buttons:
            tool_bar_button["object"] = create_tool_bar_button(
                self.tool_bar,
                tool_bar_button["icon_path"],
                tool_bar_button["hover_text"],
                tool_bar_button["status_text"],
                tool_bar_button["action"],
                tool_bar_button["checkable"],
            )

    def abort_current_action_if_any(self):
        if current_action := self.current_action.text():
            response = QMessageBox.warning(
                self,
                "Warning",
                f"Do you want to abort the current action: {current_action}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response == QMessageBox.StandardButton.Yes:
                self.current_action.setText("")
                for tool_bar_button in self.tool_bar_buttons:
                    tool_bar_button["object"].setChecked(False)

            return response == QMessageBox.StandardButton.Yes

        return True

    def no_project_open_prompt(self):
        message_box = QMessageBox()
        message_box.setWindowTitle("Information")
        message_box.setWindowIcon(self.application_icon)
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setText(
            "No project open. Do you want to create a new one or open an existing "
            "one?"
        )

        message_box.addButton("No", QMessageBox.ButtonRole.RejectRole)
        new_button = message_box.addButton("New", QMessageBox.ButtonRole.ActionRole)
        open_button = message_box.addButton("Open", QMessageBox.ButtonRole.ActionRole)

        new_button.clicked.connect(self.new_project)
        open_button.clicked.connect(self.load_project_from_file)

        message_box.exec()

    def draw_line(self, checked: bool, button: QAction, *_):
        if self.project.unscaled_pixmap.isNull():
            button.setChecked(False)
            self.no_project_open_prompt()
            return

        if checked:
            status_text = self.tool_bar_buttons[0]["status_text"]
            self.current_action.setText(status_text)
        else:
            self.current_action.setText("")
            return

        # Make the image select
        # Select point 1

        # Select point 2

    def show_pixmap(self, image: QPixmap):
        scaled_pixmap = image.scaled(
            self.image_viewer.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        self.image_viewer.setPixmap(scaled_pixmap)
        self.image_viewer.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

    def get_image_path_from_file_dialog(self):
        file_dialog = QFileDialog()
        file_dialog.setWindowTitle("Open image")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setViewMode(QFileDialog.ViewMode.Detail)
        name_filters = self.developer_config["file_handling"]["image_formats"]
        file_dialog.setNameFilters(name_filters)
        file_dialog.exec()
        filepath = get_element(file_dialog.selectedFiles(), 0, None)
        if QFileInfo(filepath).isDir():
            return
        return filepath

    def new_project(self):
        if not self.abort_current_action_if_any():
            return
        print("New project")
        if filepath := self.get_image_path_from_file_dialog():
            image = QImage(filepath)
            self.project.unscaled_pixmap = QPixmap.fromImage(image)
            pixmap = QPixmap.fromImage(image)
            self.show_pixmap(pixmap)

    def load_project_from_file(self):
        file_dialog = QFileDialog()
        file_dialog.setWindowTitle("Open project")
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setViewMode(QFileDialog.ViewMode.Detail)
        name_filters = [
            f"{self.developer_config['gui']['title']} project file (*.cimt)"
        ]
        file_dialog.setNameFilters(name_filters)
        file_dialog.exec()
        filepath = get_element(file_dialog.selectedFiles(), 0, None)
        if not filepath or QFileInfo(filepath).isDir():
            return

        with open(filepath, encoding="utf-8") as file:
            data = json.load(file)

        # TODO: Catch errors
        base_64_image_data = bytes(data["image"], encoding="utf-8")
        measurements = data["measurements"]
        image = self.image_from_base_64(base_64_image_data)
        self.project.unscaled_pixmap = QPixmap(image)
        self.project.measurements = measurements
        self.show_pixmap(self.project.unscaled_pixmap)

    def save_project_as_file(self):
        if self.project.unscaled_pixmap.isNull():
            self.no_project_open_prompt()
            return

        file_dialog = QFileDialog()
        file_dialog.setWindowTitle("Save project")
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setViewMode(QFileDialog.ViewMode.Detail)
        name_filters = [
            f"{self.developer_config['gui']['title']} project file (*.cimt)"
        ]
        file_dialog.setNameFilters(name_filters)
        file_dialog.exec()
        filepath = get_element(file_dialog.selectedFiles(), 0, None)
        if not filepath or QFileInfo(filepath).isDir():
            return
        if not filepath.endswith(".cimt"):
            filepath += ".cimt"
        self.project.save(filepath)

    def image_from_base_64(self, base_64_data):
        byte_array = QByteArray.fromBase64(base_64_data)
        return QImage.fromData(byte_array, "PNG")

    def save_project_as_image_file(self):
        print("Save project as image")

    def about(self):
        class AboutDialog(QDialog):
            def __init__(self, application_title: str, application_icon: QIcon):
                super().__init__()
                self.setWindowTitle("About")
                self.setWindowIcon(application_icon)
                icon_label = QLabel()
                icon_label.setPixmap(application_icon.pixmap(128, 128))
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

                with open("about.html", "r", encoding="utf-8") as file:
                    about_label_text = file.read().replace(
                        "{application_title}", application_title
                    )
                about_label = QLabel(about_label_text)
                about_label.setOpenExternalLinks(True)
                close_button = QPushButton("Close")
                close_button.clicked.connect(self.accept)

                layout = QVBoxLayout()
                layout.addWidget(icon_label)
                layout.addWidget(about_label)
                layout.addWidget(close_button)
                self.setLayout(layout)

                width = self.sizeHint().width()
                height = self.sizeHint().height()
                self.setFixedSize(width, height)

        if not hasattr(self, "about_dialog"):
            self.about_dialog = AboutDialog(
                self.application_title, self.application_icon
            )
        self.about_dialog.exec()

    def set_initial_window_position(self):
        (width, height) = self.config["gui"]["initial_size"]
        (initial_x, initial_y) = self.config["gui"]["initial_position"]
        screen = app.primaryScreen().availableGeometry()

        width = round(width if width > 1 else width * screen.width())
        height = round(height if height > 1 else height * screen.height())

        if initial_x == -1:
            initial_x = (screen.width() - width) // 2
        else:
            initial_x *= screen.width()

        if initial_y == -1:
            initial_y = (screen.height() - height) // 2
        else:
            initial_y *= screen.height()

        if config["gui"]["full_screen"]:
            self.showFullScreen()
        elif config["gui"]["maximized"]:
            self.showMaximized()
        else:
            self.setGeometry(initial_x, initial_y, width, height)

        if not config["gui"]["resizable"]:
            self.setFixedSize(width, height)

        window_flags = [
            [not config["gui"]["minimizable"], ~Qt.WindowType.WindowMinimizeButtonHint],
            [not config["gui"]["maximizable"], ~Qt.WindowType.WindowMaximizeButtonHint],
            [not config["gui"]["closable"], ~Qt.WindowType.WindowCloseButtonHint],
        ]
        for condition in window_flags:
            if condition[0]:
                self.setWindowFlags(self.windowFlags() & condition[1])

    def create_menu_item_bar(self) -> QAction | QMenuBar:
        def create_menu_item(parent_menu, menu_name: str, menu_item: Callable | dict):
            if callable(menu_item):
                new_menu_item = QAction(menu_name, self)
                new_menu_item.triggered.connect(menu_item)
                parent_menu.addAction(new_menu_item)
            elif isinstance(menu_item, dict):
                parent_menu = parent_menu.addMenu(menu_name)
                for parent, child in menu_item.items():
                    new_menu_item = create_menu_item(parent_menu, parent, child)
            else:
                raise ValueError("Menu item must be a callable or a dictionary.")
            return new_menu_item

        menu = {
            "File": {
                "New project": self.new_project,
                "Open project": self.load_project_from_file,
                "Save project": self.save_project_as_file,
                "Save project as image": self.save_project_as_image_file,
            },
            # "Settings": self.settings,
            "Help": {"About": self.about},
        }

        menu_bar = self.menuBar()
        for parent, child in menu.items():
            create_menu_item(menu_bar, parent, child)


def load_config(filepath):
    script_dir = Path(__file__).parent
    filepath = script_dir / filepath
    with open(filepath, "r") as file:
        return yaml.safe_load(file)


if __name__ == "__main__":
    config = load_config("config.yaml")
    developer_config = load_config("developer_config.yaml")
    app = QApplication(sys.argv)
    app.setStyle(developer_config["gui"]["style"])
    main_window = MainWindow(config, developer_config)
    main_window.show()
    sys.exit(app.exec())
