import json
import math
from pathlib import Path
from typing import Callable

import yaml
from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QCoreApplication,
    QFileInfo,
    QIODevice,
    QPoint,
    QSize,
    Qt,
)
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPen, QPixmap
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


class Project:
    def __init__(self):
        self.unscaled_pixmap = QPixmap()
        self.measurements = []

    def save(self, filepath) -> None:
        image = self.unscaled_pixmap.toImage()
        data = {
            "image": image_to_base64(image).decode("utf-8"),
            "measurements": self.measurements,
        }
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file)


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication, config: dict, developer_config: dict):
        self.app: QApplication = app
        self.config: dict = config
        self.developer_config: dict = developer_config
        self.script_dir: Path = Path(__file__).parent
        self.application_title: str = self.developer_config["gui"]["title"]
        self.application_icon: QIcon = QIcon(
            str(self.script_dir / self.developer_config["gui"]["icon"])
        )
        self.project = Project()
        self.press_position = None
        self.press_released = False

        super().__init__()
        self.setWindowTitle(self.application_title)
        self.setWindowIcon(self.application_icon)
        self.set_initial_window_position()
        self.set_window_flags()
        self.create_gui()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_position = event.pos()
            self.press_released = False

    def mouseReleaseEvent(self, event):
        if (
            self.press_position
            and event.button() == Qt.MouseButton.LeftButton
            and event.pos() in self.rect()
        ):
            self.press_released = True

    def set_initial_window_position(self):
        (width, height) = self.config["gui"]["initial_size"]
        (initial_x, initial_y) = self.config["gui"]["initial_position"]
        screen = self.app.primaryScreen().availableGeometry()

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

        if self.config["gui"]["fullscreen"]:
            self.showFullScreen()
        elif self.config["gui"]["maximized"]:
            self.showMaximized()
        else:
            self.setGeometry(initial_x, initial_y, width, height)

        if not self.config["gui"]["resizable"]:
            self.setFixedSize(width, height)

    def set_window_flags(self):
        window_flags = [
            [
                not self.config["gui"]["minimizable"],
                ~Qt.WindowType.WindowMinimizeButtonHint,
            ],
            [
                not self.config["gui"]["maximizable"],
                ~Qt.WindowType.WindowMaximizeButtonHint,
            ],
            [not self.config["gui"]["closable"], ~Qt.WindowType.WindowCloseButtonHint],
        ]
        for condition in window_flags:
            if condition[0]:
                self.setWindowFlags(self.windowFlags() & condition[1])

    def create_gui(self):
        self.create_menu_item_bar()
        self.create_tool_bar()
        self.create_pixmap_viewer()
        self.create_data_viewer()

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
                "Export to image file": self.export_to_image_file,
            },
            "Help": {"About": self.about},
        }

        menu_bar = self.menuBar()
        for parent, child in menu.items():
            create_menu_item(menu_bar, parent, child)

    def create_tool_bar(self) -> QMenuBar:
        def create_tool_bar_button(
            tool_bar: str,
            icon_path: str,
            hover_text: str,
            status_text: str,
            sub_status_text: list[str],
            action: Callable,
            checkable: bool = False,
        ) -> QAction:
            icon_path = str(self.script_dir / icon_path)
            # Using `QIcon(icon_path)` doesn't scale the icon, so pass a `QPixmap` to
            # `QIcon` instead
            icon_pixmap = QPixmap(icon_path)
            icon_pixmap = icon_pixmap.scaled(
                QSize(icon_width, icon_width), Qt.AspectRatioMode.KeepAspectRatio
            )
            icon = QIcon(icon_pixmap)
            button = QAction(icon, hover_text, self)

            button.triggered.connect(
                lambda *a: action(
                    *a,
                    button,
                    icon_path,
                    hover_text,
                    status_text,
                    sub_status_text,
                    checkable,
                )
            )
            button.setCheckable(checkable)
            tool_bar.addAction(button)
            return button

        self.tool_bar = QToolBar(self)
        icon_width = self.developer_config["gui"]["tool_bar"]["icon_width"]
        self.tool_bar.setIconSize(QSize(icon_width, icon_width))
        self.tool_bar.changeEvent = lambda *_: self.update_pixmap(
            self.project.unscaled_pixmap
        )
        self.addToolBar(self.tool_bar)

        self.status_bar = self.statusBar()
        self.status = QLabel()
        self.sub_status = QLabel()
        self.status_bar.addWidget(self.status)
        self.status_bar.addWidget(self.sub_status)
        self.set_status("", "")

        tool_bar_icons = self.developer_config["gui"]["tool_bar"]["icons"]
        self.tool_bar_buttons = [
            {
                "icon_path": tool_bar_icons["draw_line"],
                "hover_text": "Draw line",
                "status_text": "Drawing line",
                "sub_status_texts": ["Selecting point 1", "Selecting point 2"],
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
                tool_bar_button["sub_status_texts"],
                tool_bar_button["action"],
                tool_bar_button["checkable"],
            )

    def create_pixmap_viewer(self):
        self.pixmap_viewer = QLabel(self)
        self.pixmap_viewer.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.setCentralWidget(self.pixmap_viewer)

    def create_data_viewer(self):
        pass

    def new_project(self):
        if hasattr(self, "measurement_painter"):
            self.measurement_painter.eraseRect()
        self.project = Project()
        if not self.abort_current_action_if_any():
            return
        if filepath := self.get_filepath_from_file_dialog():
            self.project.unscaled_pixmap = QPixmap.fromImage(QImage(filepath))
            self.update_pixmap(self.project.unscaled_pixmap)

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
        filepath = get_element(file_dialog.selectedFiles(), 0)
        if not filepath or QFileInfo(filepath).isDir():
            return

        with open(filepath, encoding="utf-8") as file:
            data = json.load(file)
        measurements = data["measurements"]
        base64_image_data = bytes(data["image"], encoding="utf-8")
        image = base64_to_image(base64_image_data)
        self.project.unscaled_pixmap = QPixmap(image)
        self.project.measurements = measurements
        self.update_pixmap(self.project.unscaled_pixmap)

    def save_project_as_file(self):
        if self.project.unscaled_pixmap.isNull():
            self.no_project_open_prompt()
            return

        file_dialog = QFileDialog()
        file_dialog.setWindowTitle("Save project")
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setViewMode(QFileDialog.ViewMode.Detail)

        file_extension = ".cimt"
        name_filters = [
            f"{self.developer_config['gui']['title']} project file (*{file_extension})"
        ]
        file_dialog.setNameFilters(name_filters)
        file_dialog.exec()
        filepath = get_element(file_dialog.selectedFiles(), 0)
        if not filepath or QFileInfo(filepath).isDir():
            return
        if not filepath.endswith(file_extension):
            filepath += file_extension

        self.project.save(filepath)

    def export_to_image_file(self):
        print("Export to image file")

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

    def set_status(self, status: str = None, sub_status: str = None):
        if status is not None:
            self.status.setText(status)
        if sub_status is not None:
            self.sub_status.setText(sub_status)

    def draw_line(self, checked: bool, button: QAction, *_) -> None:
        # sourcery skip: extract-duplicate-method

        # So, at this point in development, I am quite stressed due to a deadline. I'm
        # developing this program to help me place measurements on images for a school
        # subject which has nothing to do with programming. Yes, it's completely
        # unnecessary. Any way: the following code is as a result going to be quite bad.
        # For this, I am sorry.

        if not checked:
            self.set_status("", "")
            return

        # If no project is open, prompt the user to open or create one. If they don't,
        # return
        if self.project.unscaled_pixmap.isNull() and self.no_project_open_prompt() == 2:
            button.setChecked(False)
            return

        status_text = self.tool_bar_buttons[0]["status_text"]
        sub_status_texts = self.tool_bar_buttons[0]["sub_status_texts"]
        self.set_status(status_text)

        pixmap = self.project.unscaled_pixmap
        if not hasattr(self, "measurement_painter"):
            self.measurement_painter = self.create_measurement_painter(pixmap)
        painter = self.measurement_painter

        self.set_status(sub_status=sub_status_texts[0])
        point_one_image_position = self.window_position_to_image_position(
            self.get_mouse_press_window_position_in_pixmap_viewer()
        )
        self.draw_point(point_one_image_position, painter, pixmap)

        self.set_status(sub_status=sub_status_texts[1])
        point_two_image_position = self.window_position_to_image_position(
            self.get_mouse_press_window_position_in_pixmap_viewer()
        )
        self.draw_point(point_two_image_position, painter, pixmap)

        self.project.measurements.append(
            [point_one_image_position, point_two_image_position]
        )

        self.set_status("", "")
        button.setChecked(False)

    def draw_extension_lines(self, point_one, point_two, painter, pixmap):
        x_1 = point_one[0]
        y_1 = point_one[1]

        x_2 = point_two[0]
        y_2 = point_two[1]

        m = (y_2 - y_1) / (x_2 - x_1)
        b = y_1 - m * x_1

        perpendicular_m = -1 / m
        y = lambda x: perpendicular_m * x + b

    def draw_point(
        self,
        image_position: tuple[int, int],
        painter: QPainter,
        pixmap: QPixmap,
        update: bool = True,
    ) -> None:
        painter.drawPoint(*image_position)
        if update:
            self.update_pixmap(pixmap)

    def create_measurement_painter(self, pixmap: QPixmap) -> QPainter:
        smallest_dimension = min(pixmap.width(), pixmap.height())
        color = QColor.fromRgb(*self.get_preview_guide_color())
        width = self.get_line_width(smallest_dimension)
        pen = QPen()
        pen.setColor(color)
        pen.setWidth(width)
        painter = QPainter(pixmap)
        painter.setPen(pen)
        return painter

    def get_line_width(self, smallest_dimension: int) -> int:
        return math.ceil(
            self.config["measurement_rendering"]["line_width"] * smallest_dimension
        )

    def get_mouse_press_window_position_in_pixmap_viewer(self) -> tuple[int, int]:
        while self.isVisible():
            position = self.get_mouse_press_window_position()
            global_position = self.mapToGlobal(QPoint(*position))
            local_position = self.pixmap_viewer.mapFromGlobal(global_position)
            pixmap = self.pixmap_viewer.pixmap()
            if (
                0 <= local_position.x() <= pixmap.width()
                and 0 <= local_position.y() <= pixmap.height()
            ):
                return (local_position.x(), local_position.y())

    def window_position_to_image_position(
        self, position: tuple[int, int]
    ) -> tuple[int, int]:
        pixmap = self.pixmap_viewer.pixmap()
        x = position[0] * self.project.unscaled_pixmap.width() / pixmap.width()
        y = position[1] * self.project.unscaled_pixmap.height() / pixmap.height()
        return (int(x), int(y))

    def get_mouse_press_window_position(self) -> tuple[int, int]:
        self.press_position = None
        self.press_released = False
        while self.isVisible() and not self.press_position and not self.press_released:
            QCoreApplication.processEvents()
        return (self.press_position.x(), self.press_position.y())

    def update_pixmap(self, image: QPixmap):
        scaled_pixmap = image.scaled(
            self.pixmap_viewer.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        self.pixmap_viewer.setPixmap(scaled_pixmap)
        self.pixmap_viewer.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

    def abort_current_action_if_any(self):
        if status := self.status.text():
            response = QMessageBox.warning(
                self,
                "Warning",
                f"Do you want to abort the current action: {status}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response == QMessageBox.StandardButton.Yes:
                self.status.setText("")
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
            "No project is currently open. Do you want to open an existing project or "
            "create a new one?"
        )

        message_box.addButton("No", QMessageBox.ButtonRole.RejectRole)
        new_button = message_box.addButton("New", QMessageBox.ButtonRole.ActionRole)
        new_button.clicked.connect(self.new_project)

        open_button = message_box.addButton("Open", QMessageBox.ButtonRole.ActionRole)
        open_button.clicked.connect(self.load_project_from_file)

        return message_box.exec()

    def get_filepath_from_file_dialog(self):
        file_dialog = QFileDialog()
        file_dialog.setWindowTitle("Open image")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setViewMode(QFileDialog.ViewMode.Detail)
        name_filters = self.developer_config["file_handling"]["image_formats"]
        file_dialog.setNameFilters(name_filters)
        file_dialog.exec()
        filepath = get_element(file_dialog.selectedFiles(), 0)
        if QFileInfo(filepath).isDir():
            return
        return filepath

    def paintEvent(self, _):
        pass

    def resizeEvent(self, _):
        unscaled_pixmap = self.project.unscaled_pixmap
        if unscaled_pixmap.isNull():
            return

        # According to my own testing, images whose largest dimension is 64 or less look
        # better when `Qt.TransformationMode.FastTransformation` is used, while larger
        # images look better when `Qt.TransformationMode.SmoothTransformation` is used.
        # TODO Consider using a more sophisticated algorithm to determine the best
        # transformation mode. Nearest neighbor interpolation might be better for pixel
        # accuracy, which is important for the measurements.
        largest_size = max(unscaled_pixmap.width(), unscaled_pixmap.height())
        if largest_size > 64:
            transformation_mode = Qt.TransformationMode.SmoothTransformation
        else:
            transformation_mode = Qt.TransformationMode.FastTransformation

        scaled_image = unscaled_pixmap.scaled(
            self.pixmap_viewer.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            transformation_mode,
        )
        self.pixmap_viewer.setPixmap(scaled_image)

    def draw_measurements(self):
        print("Drawing measurements")
        pixmap = self.project.unscaled_pixmap
        self.measurement_painter = self.create_measurement_painter(pixmap)
        print(self.project.measurements)
        for measurement in self.project.measurements:
            point_one = measurement[0]
            point_two = measurement[1]
            self.measurement_painter.drawLine(*point_one, *point_two)
        # self.update_pixmap(pixmap)

    def get_preview_guide_color(self) -> list[int]:
        return self.config["measurement_rendering"]["preview_guide_color"]


def get_element(object, index, fallback=None):
    try:
        return object[index]
    except IndexError:
        return fallback


def image_to_base64(image: QImage):
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # TODO Save with the format it was imported with
    return byte_array.toBase64().data()


def base64_to_image(base64_data):
    byte_array = QByteArray.fromBase64(base64_data)
    return QImage.fromData(byte_array, "PNG")


def load_config(filepath):
    script_dir = Path(__file__).parent
    filepath = script_dir / filepath
    with open(filepath, "r") as file:
        return yaml.safe_load(file)


if __name__ == "__main__":
    import sys

    config = load_config("config.yaml")
    developer_config = load_config("developer_config.yaml")
    app = QApplication(sys.argv)
    app.setStyle(developer_config["gui"]["style"])
    main_window = MainWindow(app, config, developer_config)
    main_window.show()
    sys.exit(app.exec())
