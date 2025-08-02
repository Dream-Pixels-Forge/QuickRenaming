import os
import re
import time
import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Set
import logging
from datetime import datetime
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# Try to import customtkinter, fallback to tkinter
try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox, ttk, StringVar, BooleanVar, IntVar
    USE_CUSTOM_TK = True
except ImportError:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk, StringVar, BooleanVar, IntVar
    USE_CUSTOM_TK = False
    # Create ctk alias for standard tkinter

    class ctk:
        CTk = tk.Tk
        CTkFrame = tk.Frame
        CTkLabel = tk.Label
        CTkButton = tk.Button
        CTkEntry = tk.Entry
        CTkOptionMenu = ttk.Combobox
        CTkCheckBox = tk.Checkbutton
        CTkSlider = tk.Scale
        CTkProgressBar = ttk.Progressbar
        CTkScrollbar = tk.Scrollbar
        CTkToplevel = tk.Toplevel

        @staticmethod
        def set_appearance_mode(mode):
            pass

        @staticmethod
        def set_default_color_theme(theme):
            pass

        class CTkFont:
            def __init__(self, size=12, weight="normal"):
                self.size = size
                self.weight = weight

# Try to import PIL, make it optional
try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    Image.MAX_IMAGE_PIXELS = None
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL not available. Image conversion features will be disabled.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("quick_renaming.log"),
        logging.StreamHandler()
    ]
)


class QuickRenamingApp:
    # Extension presets with enhanced categories
    EXTENSION_PRESETS = {
        'Images': ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.tiff', '*.webp', '*.svg', '*.ico'],
        'Documents': ['*.pdf', '*.doc', '*.docx', '*.txt', '*.rtf', '*.odt', '*.xls', '*.xlsx', '*.csv', '*.ppt', '*.pptx'],
        'Audio': ['*.mp3', '*.wav', '*.ogg', '*.flac', '*.m4a', '*.wma', '*.aac', '*.opus'],
        'Video': ['*.mp4', '*.avi', '*.mov', '*.wmv', '*.flv', '*.mkv', '*.webm', '*.m4v', '*.3gp'],
        'Code': ['*.py', '*.js', '*.html', '*.css', '*.cpp', '*.c', '*.java', '*.php', '*.rb', '*.go'],
        'Archives': ['*.zip', '*.rar', '*.7z', '*.tar', '*.gz', '*.bz2', '*.xz'],
        'All Files': ['*.*']
    }

    # Rename patterns with descriptions
    RENAME_PATTERNS = {
        'Sequential': 'file_{n:03d}',
        'Date + Sequential': '{date}_{n:03d}',
        'Original + Number': '{name}_{n:02d}',
        'Timestamp': '{date}_{time}_{n:02d}',
        'Custom': ''
    }

    # Supported image formats for conversion with format-specific settings
    IMAGE_CONVERSION_FORMATS = {
        'JPEG': {'ext': '.jpg', 'supports_alpha': False, 'default_quality': 85},
        'PNG': {'ext': '.png', 'supports_alpha': True, 'default_compression': 6},
        'GIF': {'ext': '.gif', 'supports_alpha': True},
        'BMP': {'ext': '.bmp', 'supports_alpha': False},
        'WEBP': {'ext': '.webp', 'supports_alpha': True, 'default_quality': 80}
    }

    def __init__(self, root):
        self.root = root
        self.root.title("QuickRenaming Pro - Advanced File Manager")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)

        # Configure bento grid layout
        self.root.grid_columnconfigure(0, weight=2)  # Left panel
        self.root.grid_columnconfigure(1, weight=3)  # Main panel
        self.root.grid_columnconfigure(2, weight=1)  # Right panel
        self.root.grid_rowconfigure(0, weight=1)

        # Set appearance (only for customtkinter)
        if USE_CUSTOM_TK:
            ctk.set_appearance_mode("Dark")
            ctk.set_default_color_theme("blue")

        # Enhanced variables
        self.files: List[Path] = []
        self.filtered_files: List[Path] = []
        self.current_directory = Path.cwd()
        self.preview_data: List[Dict[str, Any]] = []
        self.undo_stack: List[Dict[str, Any]] = []
        self.selected_preset = StringVar(value='Images')
        self.convert_format = StringVar(value='JPEG')
        self.search_var = StringVar()
        self.case_sensitive = BooleanVar()
        self.recursive_search = BooleanVar(value=True)
        self.file_size_filter = StringVar(value='All')
        self.selected_pattern = StringVar(value='Sequential')

        # Additional variables
        self.bg_color = StringVar(value="#FFFFFF")
        self.keep_original = BooleanVar()
        self.override_existing = BooleanVar()

        # Statistics
        self.stats = {
            'total_files': 0,
            'selected_files': 0,
            'total_size': 0,
            'operations_count': 0
        }

        # Create bento grid UI
        self.create_bento_layout()

        # Load settings
        self.load_settings()

        # Bind events
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.search_var.trace('w', self.filter_files)

    def create_bento_layout(self):
        """Create modern bento grid layout"""
        self.create_left_panel()
        self.create_main_panel()
        self.create_right_panel()
        self.create_status_bar()

    def create_left_panel(self):
        """Create left panel with file browser and filters"""
        if USE_CUSTOM_TK:
            left_panel = ctk.CTkFrame(self.root, corner_radius=15)
        else:
            left_panel = ctk.CTkFrame(self.root)
        left_panel.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        left_panel.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkLabel(left_panel, text="📁 File Browser",
                              font=ctk.CTkFont(size=16, weight="bold") if USE_CUSTOM_TK else ("Arial", 16, "bold"))
        header.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        # Directory selection
        if USE_CUSTOM_TK:
            dir_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        else:
            dir_frame = ctk.CTkFrame(left_panel)
        dir_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        dir_frame.grid_columnconfigure(0, weight=1)

        self.dir_entry = ctk.CTkEntry(dir_frame)
        self.dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.dir_entry.insert(0, str(self.current_directory))

        browse_btn = ctk.CTkButton(
            dir_frame, text="📂", width=40, command=self.browse_directory)
        browse_btn.grid(row=0, column=1)

        # File type presets
        if USE_CUSTOM_TK:
            preset_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        else:
            preset_frame = ctk.CTkFrame(left_panel)
        preset_frame.grid(row=2, column=0, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(preset_frame, text="File Type:",
                     font=ctk.CTkFont(weight="bold") if USE_CUSTOM_TK else ("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))

        if USE_CUSTOM_TK:
            self.preset_menu = ctk.CTkOptionMenu(preset_frame,
                                                 values=list(
                                                     self.EXTENSION_PRESETS.keys()),
                                                 variable=self.selected_preset,
                                                 command=self.on_preset_select)
        else:
            self.preset_menu = ttk.Combobox(preset_frame,
                                            values=list(
                                                self.EXTENSION_PRESETS.keys()),
                                            textvariable=self.selected_preset,
                                            state="readonly")
            self.preset_menu.bind('<<ComboboxSelected>>', lambda e: self.on_preset_select(
                self.selected_preset.get()))

        self.preset_menu.grid(row=1, column=0, sticky="ew")

        # Custom pattern
        self.pattern_entry = ctk.CTkEntry(preset_frame)
        self.pattern_entry.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        self.pattern_entry.insert(0, "*.jpg, *.png")

        # Search and filters
        filter_frame = ctk.CTkFrame(left_panel)
        filter_frame.grid(row=3, column=0, padx=15, pady=10, sticky="ew")
        filter_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(filter_frame, text="🔍 Filters",
                     font=ctk.CTkFont(size=14, weight="bold") if USE_CUSTOM_TK else ("Arial", 14, "bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

        # Search box
        self.search_entry = ctk.CTkEntry(
            filter_frame, textvariable=self.search_var)
        self.search_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Filter options
        if USE_CUSTOM_TK:
            options_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        else:
            options_frame = ctk.CTkFrame(filter_frame)
        options_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.case_check = ctk.CTkCheckBox(
            options_frame, text="Case sensitive", variable=self.case_sensitive)
        self.case_check.grid(row=0, column=0, sticky="w", pady=2)

        self.recursive_check = ctk.CTkCheckBox(
            options_frame, text="Include subfolders", variable=self.recursive_search)
        self.recursive_check.grid(row=1, column=0, sticky="w", pady=2)

        # Size filter
        ctk.CTkLabel(options_frame, text="Size:").grid(
            row=2, column=0, sticky="w", pady=(10, 2))

        if USE_CUSTOM_TK:
            size_menu = ctk.CTkOptionMenu(options_frame,
                                          values=["All", "< 1MB", "1-10MB",
                                                  "10-100MB", "> 100MB"],
                                          variable=self.file_size_filter,
                                          command=self.filter_files)
        else:
            size_menu = ttk.Combobox(options_frame,
                                     values=["All", "< 1MB", "1-10MB",
                                             "10-100MB", "> 100MB"],
                                     textvariable=self.file_size_filter,
                                     state="readonly")
            size_menu.bind('<<ComboboxSelected>>',
                           lambda e: self.filter_files())

        size_menu.grid(row=3, column=0, sticky="ew", pady=2)

        # Load files button
        load_btn = ctk.CTkButton(left_panel, text="🔄 Load Files",
                                 command=self.load_files, height=40 if USE_CUSTOM_TK else None,
                                 font=ctk.CTkFont(weight="bold") if USE_CUSTOM_TK else ("Arial", 10, "bold"))
        load_btn.grid(row=4, column=0, padx=15, pady=15, sticky="ew")

    def create_main_panel(self):
        """Create main panel with file list and operations"""
        if USE_CUSTOM_TK:
            main_panel = ctk.CTkFrame(self.root, corner_radius=15)
        else:
            main_panel = ctk.CTkFrame(self.root)
        main_panel.grid(row=0, column=1, padx=5, pady=10, sticky="nsew")
        main_panel.grid_columnconfigure(0, weight=1)
        main_panel.grid_rowconfigure(1, weight=1)

        # Header with file count
        if USE_CUSTOM_TK:
            header_frame = ctk.CTkFrame(main_panel, fg_color="transparent")
        else:
            header_frame = ctk.CTkFrame(main_panel)
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header_frame, text="📋 File Operations",
                     font=ctk.CTkFont(size=16, weight="bold") if USE_CUSTOM_TK else ("Arial", 16, "bold")).grid(row=0, column=0, sticky="w")

        self.file_count_label = ctk.CTkLabel(header_frame, text="0 files",
                                             font=ctk.CTkFont(size=12) if USE_CUSTOM_TK else ("Arial", 12))
        self.file_count_label.grid(row=0, column=1, sticky="e")

        # File list with enhanced treeview
        list_frame = ctk.CTkFrame(main_panel)
        list_frame.grid(row=1, column=0, padx=15, pady=10, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        # Enhanced treeview
        if USE_CUSTOM_TK:
            self.tree_scroll_y = ctk.CTkScrollbar(list_frame, orientation="vertical")
            self.tree_scroll_x = ctk.CTkScrollbar(list_frame, orientation="horizontal")
        else:
            self.tree_scroll_y = tk.Scrollbar(list_frame, orient="vertical")
            self.tree_scroll_x = tk.Scrollbar(list_frame, orient="horizontal")

        self.tree = ttk.Treeview(list_frame,
                                 columns=("original", "new_name",
                                          "size", "modified", "status"),
                                 show="headings",
                                 yscrollcommand=self.tree_scroll_y.set,
                                 xscrollcommand=self.tree_scroll_x.set)

        # Configure columns
        self.tree.heading("original", text="Original Name")
        self.tree.heading("new_name", text="New Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Modified")
        self.tree.heading("status", text="Status")

        self.tree.column("original", width=250, minwidth=150)
        self.tree.column("new_name", width=250, minwidth=150)
        self.tree.column("size", width=80, minwidth=60, anchor="center")
        self.tree.column("modified", width=120, minwidth=100, anchor="center")
        self.tree.column("status", width=80, minwidth=60, anchor="center")

        # Grid treeview and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree_scroll_x.grid(row=1, column=0, sticky="ew")

        self.tree_scroll_y.configure(command=self.tree.yview)
        self.tree_scroll_x.configure(command=self.tree.xview)

        # Rename options panel
        self.create_rename_panel(main_panel)

        # Action buttons
        self.create_action_buttons(main_panel)

    def create_rename_panel(self, parent):
        """Create rename options panel"""
        rename_frame = ctk.CTkFrame(parent)
        rename_frame.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        rename_frame.grid_columnconfigure(1, weight=1)

        # Header
        ctk.CTkLabel(rename_frame, text="✏️ Rename Options",
                     font=ctk.CTkFont(size=14, weight="bold") if USE_CUSTOM_TK else ("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4,
                                                                                                                padx=15, pady=(15, 10), sticky="w")

        # Pattern selection
        ctk.CTkLabel(rename_frame, text="Pattern:").grid(
            row=1, column=0, padx=(15, 5), pady=5, sticky="w")

        if USE_CUSTOM_TK:
            pattern_menu = ctk.CTkOptionMenu(rename_frame,
                                             values=list(
                                                 self.RENAME_PATTERNS.keys()),
                                             variable=self.selected_pattern,
                                             command=self.on_pattern_select)
        else:
            pattern_menu = ttk.Combobox(rename_frame,
                                        values=list(
                                            self.RENAME_PATTERNS.keys()),
                                        textvariable=self.selected_pattern,
                                        state="readonly")
            pattern_menu.bind('<<ComboboxSelected>>', lambda e: self.on_pattern_select(
                self.selected_pattern.get()))

        pattern_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Custom pattern entry
        self.rename_pattern = StringVar(
            value=self.RENAME_PATTERNS['Sequential'])
        self.pattern_custom_entry = ctk.CTkEntry(
            rename_frame, textvariable=self.rename_pattern)
        self.pattern_custom_entry.grid(
            row=1, column=2, padx=5, pady=5, sticky="ew")

        # Start number
        ctk.CTkLabel(rename_frame, text="Start:").grid(
            row=1, column=3, padx=(15, 5), pady=5, sticky="w")
        self.start_number = IntVar(value=1)
        start_entry = ctk.CTkEntry(
            rename_frame, textvariable=self.start_number, width=60)
        start_entry.grid(row=1, column=4, padx=(5, 15), pady=5)

        # Preview button
        preview_btn = ctk.CTkButton(rename_frame, text="👁️ Preview",
                                    command=self.preview_rename, width=100)
        preview_btn.grid(row=2, column=0, columnspan=5, padx=15, pady=10)

    def create_action_buttons(self, parent):
        """Create action buttons panel"""
        if USE_CUSTOM_TK:
            action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        else:
            action_frame = ctk.CTkFrame(parent)
        action_frame.grid(row=3, column=0, padx=15, pady=(0, 15), sticky="ew")

        # Main action buttons
        if USE_CUSTOM_TK:
            self.rename_btn = ctk.CTkButton(action_frame, text="✅ Execute Rename",
                                            command=self.rename_files, state="disabled",
                                            fg_color="#2e8b57", hover_color="#3cb371",
                                            font=ctk.CTkFont(weight="bold"), height=40)
            self.undo_btn = ctk.CTkButton(action_frame, text="↶ Undo",
                                          command=self.undo_operation, state="disabled",
                                          fg_color="#ff8c00", hover_color="#ffa500", height=40)
            self.clear_btn = ctk.CTkButton(action_frame, text="🗑️ Clear",
                                           command=self.clear_list,
                                           fg_color="#8b0000", hover_color="#a52a2a", height=40)
        else:
            self.rename_btn = ctk.CTkButton(action_frame, text="✅ Execute Rename",
                                            command=self.rename_files, state="disabled")
            self.undo_btn = ctk.CTkButton(action_frame, text="↶ Undo",
                                          command=self.undo_operation, state="disabled")
            self.clear_btn = ctk.CTkButton(action_frame, text="🗑️ Clear",
                                           command=self.clear_list)

        self.rename_btn.pack(side="right", padx=5)
        self.undo_btn.pack(side="right", padx=5)
        self.clear_btn.pack(side="right", padx=5)

    def create_right_panel(self):
        """Create right panel with tools and statistics"""
        if USE_CUSTOM_TK:
            right_panel = ctk.CTkFrame(self.root, corner_radius=15)
        else:
            right_panel = ctk.CTkFrame(self.root)
        right_panel.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)

        # Statistics panel
        self.create_stats_panel(right_panel)

        # Image conversion panel (only if PIL is available)
        if HAS_PIL:
            self.create_conversion_panel(right_panel)

        # Quick tools panel
        self.create_tools_panel(right_panel)

    def create_stats_panel(self, parent):
        """Create statistics panel"""
        stats_frame = ctk.CTkFrame(parent)
        stats_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")

        ctk.CTkLabel(stats_frame, text="📊 Statistics",
                     font=ctk.CTkFont(size=14, weight="bold") if USE_CUSTOM_TK else ("Arial", 14, "bold")).grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        # Stats labels
        self.stats_labels = {}
        stats_items = [("Total Files:", "total_files"), ("Selected:", "selected_files"),
                       ("Total Size:", "total_size"), ("Operations:", "operations_count")]

        for i, (label, key) in enumerate(stats_items):
            ctk.CTkLabel(stats_frame, text=label).grid(
                row=i+1, column=0, padx=15, pady=2, sticky="w")
            self.stats_labels[key] = ctk.CTkLabel(stats_frame, text="0")
            self.stats_labels[key].grid(
                row=i+1, column=1, padx=15, pady=2, sticky="e")

    def create_conversion_panel(self, parent):
        """Create image conversion panel"""
        conv_frame = ctk.CTkFrame(parent)
        conv_frame.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        conv_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(conv_frame, text="🖼️ Image Conversion",
                     font=ctk.CTkFont(size=14, weight="bold") if USE_CUSTOM_TK else ("Arial", 14, "bold")).grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        # Enable conversion
        self.convert_check = ctk.CTkCheckBox(
            conv_frame, text="Enable conversion")
        self.convert_check.grid(row=1, column=0, padx=15, pady=5, sticky="w")

        # Format selection
        ctk.CTkLabel(conv_frame, text="Format:").grid(
            row=2, column=0, padx=15, pady=(10, 2), sticky="w")

        if USE_CUSTOM_TK:
            self.convert_format_menu = ctk.CTkOptionMenu(conv_frame,
                                                         values=list(
                                                             self.IMAGE_CONVERSION_FORMATS.keys()),
                                                         variable=self.convert_format)
        else:
            self.convert_format_menu = ttk.Combobox(conv_frame,
                                                    values=list(
                                                        self.IMAGE_CONVERSION_FORMATS.keys()),
                                                    textvariable=self.convert_format,
                                                    state="readonly")

        self.convert_format_menu.grid(
            row=3, column=0, padx=15, pady=2, sticky="ew")

        # Quality slider
        ctk.CTkLabel(conv_frame, text="Quality:").grid(
            row=4, column=0, padx=15, pady=(10, 2), sticky="w")

        if USE_CUSTOM_TK:
            self.quality_slider = ctk.CTkSlider(
                conv_frame, from_=1, to=100, number_of_steps=99)
            self.quality_slider.set(85)
            self.quality_slider.grid(
                row=5, column=0, padx=15, pady=2, sticky="ew")

            self.quality_label = ctk.CTkLabel(conv_frame, text="85%")
            self.quality_label.grid(row=6, column=0, padx=15, pady=2)
            self.quality_slider.configure(
                command=lambda v: self.quality_label.configure(text=f"{int(v)}%"))
        else:
            self.quality_slider = tk.Scale(
                conv_frame, from_=1, to=100, orient="horizontal")
            self.quality_slider.set(85)
            self.quality_slider.grid(
                row=5, column=0, padx=15, pady=2, sticky="ew")

            self.quality_label = ctk.CTkLabel(conv_frame, text="85%")
            self.quality_label.grid(row=6, column=0, padx=15, pady=2)
            self.quality_slider.configure(
                command=lambda v: self.quality_label.configure(text=f"{int(float(v))}%"))

        # Resize options
        self.resize_var = BooleanVar()
        resize_check = ctk.CTkCheckBox(
            conv_frame, text="Resize images", variable=self.resize_var)
        resize_check.grid(row=7, column=0, padx=15, pady=(10, 5), sticky="w")

        if USE_CUSTOM_TK:
            resize_frame = ctk.CTkFrame(conv_frame, fg_color="transparent")
        else:
            resize_frame = ctk.CTkFrame(conv_frame)
        resize_frame.grid(row=8, column=0, padx=15, pady=5, sticky="ew")
        resize_frame.grid_columnconfigure(0, weight=1)
        resize_frame.grid_columnconfigure(2, weight=1)

        self.width_var = StringVar(value="800")
        self.height_var = StringVar(value="600")
        self.keep_aspect_var = BooleanVar(value=True)

        width_entry = ctk.CTkEntry(
            resize_frame, textvariable=self.width_var, width=60)
        width_entry.grid(row=0, column=0, padx=2, sticky="ew")

        ctk.CTkLabel(resize_frame, text="×").grid(row=0, column=1, padx=5)

        height_entry = ctk.CTkEntry(
            resize_frame, textvariable=self.height_var, width=60)
        height_entry.grid(row=0, column=2, padx=2, sticky="ew")

        # Keep aspect ratio option
        aspect_check = ctk.CTkCheckBox(
            resize_frame, text="Keep aspect ratio", variable=self.keep_aspect_var)
        aspect_check.grid(row=1, column=0, columnspan=3,
                          pady=(5, 0), sticky="w")

    def create_tools_panel(self, parent):
        """Create quick tools panel"""
        tools_frame = ctk.CTkFrame(parent)
        tools_frame.grid(row=2 if HAS_PIL else 1, column=0,
                         padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(tools_frame, text="🛠️ Quick Tools",
                     font=ctk.CTkFont(size=14, weight="bold") if USE_CUSTOM_TK else ("Arial", 14, "bold")).grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        # Tool buttons
        tools = [
            ("📁 Open Folder", self.open_current_folder),
            ("💾 Save Settings", self.save_settings),
            ("📋 Export List", self.export_file_list),
            ("🔄 Refresh", self.refresh_files),
            ("ℹ️ About", self.show_about)
        ]

        for i, (text, command) in enumerate(tools):
            btn = ctk.CTkButton(
                tools_frame, text=text, command=command, height=35 if USE_CUSTOM_TK else None)
            btn.grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")

    def create_status_bar(self):
        """Create status bar at bottom"""
        self.status_var = StringVar(value="Ready")
        if USE_CUSTOM_TK:
            status_frame = ctk.CTkFrame(self.root, height=30, corner_radius=0)
        else:
            status_frame = ctk.CTkFrame(self.root, height=30)
        status_frame.grid(row=1, column=0, columnspan=3,
                          sticky="ew", padx=10, pady=(0, 10))

        status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var,
                                    font=ctk.CTkFont(size=11) if USE_CUSTOM_TK else ("Arial", 11))
        status_label.pack(side="left", padx=15, pady=5)

    def browse_directory(self):
        """Open directory selection dialog"""
        directory = filedialog.askdirectory(initialdir=self.current_directory)
        if directory:
            self.current_directory = Path(directory)
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, str(self.current_directory))

    def on_preset_select(self, choice):
        """Handle preset selection"""
        if choice in self.EXTENSION_PRESETS:
            patterns = self.EXTENSION_PRESETS[choice]
            self.pattern_entry.delete(0, 'end')
            self.pattern_entry.insert(0, ", ".join(patterns))

    def get_file_patterns(self) -> List[str]:
        """Get file patterns from entry or selected preset"""
        pattern = self.pattern_entry.get().strip()
        if not pattern and self.selected_preset.get() in self.EXTENSION_PRESETS:
            return self.EXTENSION_PRESETS[self.selected_preset.get()]
        return [p.strip() for p in pattern.split(",") if p.strip()]

    def on_pattern_select(self, choice):
        """Handle pattern selection"""
        if choice in self.RENAME_PATTERNS:
            pattern = self.RENAME_PATTERNS[choice]
            if pattern:  # Not custom
                self.rename_pattern.set(pattern)
                if USE_CUSTOM_TK:
                    self.pattern_custom_entry.configure(state="disabled")
            else:  # Custom
                if USE_CUSTOM_TK:
                    self.pattern_custom_entry.configure(state="normal")
                    self.pattern_custom_entry.focus()

    def filter_files(self, *args):
        """Filter files based on search criteria"""
        if not self.files:
            return

        search_term = self.search_var.get().lower()
        if not search_term:
            self.filtered_files = self.files.copy()
        else:
            if self.case_sensitive.get():
                self.filtered_files = [
                    f for f in self.files if search_term in f.name]
            else:
                self.filtered_files = [
                    f for f in self.files if search_term in f.name.lower()]

        # Apply size filter
        size_filter = self.file_size_filter.get()
        if size_filter != "All":
            filtered_by_size = []
            for f in self.filtered_files:
                try:
                    size = f.stat().st_size
                    if size_filter == "< 1MB" and size < 1024*1024:
                        filtered_by_size.append(f)
                    elif size_filter == "1-10MB" and 1024*1024 <= size < 10*1024*1024:
                        filtered_by_size.append(f)
                    elif size_filter == "10-100MB" and 10*1024*1024 <= size < 100*1024*1024:
                        filtered_by_size.append(f)
                    elif size_filter == "> 100MB" and size >= 100*1024*1024:
                        filtered_by_size.append(f)
                except OSError:
                    continue
            self.filtered_files = filtered_by_size

        self.update_file_list()
        self.update_stats()

    def update_file_list(self):
        """Update the file list display"""
        self.tree.delete(*self.tree.get_children())

        for file_path in self.filtered_files:
            try:
                stat = file_path.stat()
                size = self.format_size(stat.st_size)
                modified = datetime.fromtimestamp(
                    stat.st_mtime).strftime("%Y-%m-%d %H:%M")

                self.tree.insert("", "end", values=(
                    file_path.name,
                    "",  # New name will be filled during preview
                    size,
                    modified,
                    "Ready"
                ))
            except OSError:
                continue

        self.file_count_label.configure(
            text=f"{len(self.filtered_files)} files")

    def format_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"

    def update_stats(self):
        """Update statistics display"""
        self.stats['total_files'] = len(self.files)
        self.stats['selected_files'] = len(self.filtered_files)

        total_size = 0
        for f in self.filtered_files:
            try:
                total_size += f.stat().st_size
            except OSError:
                continue
        self.stats['total_size'] = total_size

        # Update labels
        self.stats_labels['total_files'].configure(
            text=str(self.stats['total_files']))
        self.stats_labels['selected_files'].configure(
            text=str(self.stats['selected_files']))
        self.stats_labels['total_size'].configure(
            text=self.format_size(self.stats['total_size']))
        self.stats_labels['operations_count'].configure(
            text=str(self.stats['operations_count']))

    def load_files(self):
        """Load files based on pattern with enhanced filtering"""
        try:
            self.files = []
            patterns = self.get_file_patterns()

            if not patterns:
                messagebox.showwarning(
                    "Warning", "Please select a file type or enter a pattern")
                return

            # Clear previous data
            self.tree.delete(*self.tree.get_children())
            self.preview_data = []

            # Update directory from entry
            dir_path = self.dir_entry.get().strip()
            if dir_path and Path(dir_path).exists():
                self.current_directory = Path(dir_path)

            # Collect files matching patterns
            matched_files = set()

            for p in patterns:
                p = p.strip()
                if '*' in p or '?' in p:
                    if self.recursive_search.get():
                        matched_files.update(self.current_directory.rglob(p))
                    else:
                        matched_files.update(self.current_directory.glob(p))

            # Filter out directories, keep only files
            self.files = sorted([f for f in matched_files if f.is_file()],
                                key=lambda x: x.name.lower())

            if not self.files:
                self.status_var.set(
                    f"No files found matching pattern: {', '.join(patterns)}")
                self.update_stats()
                return

            # Apply initial filtering
            self.filtered_files = self.files.copy()
            self.filter_files()

            self.status_var.set(f"Loaded {len(self.files)} files")
            logging.info(
                f"Loaded {len(self.files)} files from {self.current_directory}")

        except Exception as e:
            logging.error(f"Error loading files: {e}")
            messagebox.showerror("Error", f"Failed to load files: {e}")
            self.status_var.set("Error loading files")

    def preview_rename(self):
        """Preview the rename operation with enhanced formatting"""
        if not self.filtered_files:
            messagebox.showwarning("Warning", "No files loaded")
            return

        try:
            self.tree.delete(*self.tree.get_children())
            self.preview_data = []

            pattern = self.rename_pattern.get().strip()
            if not pattern:
                messagebox.showwarning(
                    "Warning", "Please enter a rename pattern")
                return

            counter = self.start_number.get()
            current_date = datetime.now()

            # Check if conversion is enabled
            convert_images = HAS_PIL and hasattr(
                self, 'convert_check') and self.convert_check.get()
            target_format = self.convert_format.get()

            for i, file_path in enumerate(self.filtered_files, 1):
                try:
                    # Get file stats
                    stat = file_path.stat()
                    file_date = datetime.fromtimestamp(stat.st_mtime)

                    # Generate new name with enhanced variables
                    new_name = pattern.format(
                        n=counter,
                        i=i,
                        name=file_path.stem,
                        ext=file_path.suffix[1:],  # without dot
                        date=current_date.strftime("%Y%m%d"),
                        time=current_date.strftime("%H%M%S"),
                        year=current_date.year,
                        month=current_date.month,
                        day=current_date.day,
                        file_date=file_date.strftime("%Y%m%d"),
                        file_year=file_date.year,
                        file_month=file_date.month,
                        file_day=file_date.day,
                        size=stat.st_size,
                        parent=file_path.parent.name
                    )

                    # Handle image conversion extension change
                    if convert_images and self.is_image_file(file_path):
                        target_ext = self.IMAGE_CONVERSION_FORMATS[target_format]['ext']
                        if not new_name.endswith(target_ext):
                            # Remove old extension and add new one
                            if new_name.endswith(file_path.suffix):
                                new_name = new_name[:-len(file_path.suffix)]
                            new_name += target_ext
                    else:
                        # Add original extension if not in pattern
                        if not new_name.endswith(file_path.suffix):
                            new_name += file_path.suffix

                    # Create preview data
                    size = self.format_size(stat.st_size)
                    modified = file_date.strftime("%Y-%m-%d %H:%M")

                    self.preview_data.append({
                        "original": file_path.name,
                        "new_name": new_name,
                        "original_path": file_path,
                        "new_path": file_path.parent / new_name,
                        "status": "Ready",
                        "size": size,
                        "modified": modified
                    })

                    counter += 1

                except Exception as e:
                    logging.warning(f"Error processing {file_path}: {e}")
                    continue

            # Update treeview with enhanced data
            for item in self.preview_data:
                self.tree.insert("", "end", values=(
                    item["original"],
                    item["new_name"],
                    item["size"],
                    item["modified"],
                    item["status"]
                ))

            self.rename_btn.configure(state="normal")
            self.status_var.set(
                f"Preview ready. {len(self.preview_data)} files will be renamed.")

        except Exception as e:
            logging.error(f"Error generating preview: {e}")
            messagebox.showerror("Error", f"Failed to generate preview: {e}")

    def convert_image(self, src_path: Path, dest_path: Path, format_name: str) -> bool:
        """Convert an image to the specified format"""
        if not HAS_PIL:
            return False

        try:
            with Image.open(src_path) as img:
                # Get quality setting
                quality = int(self.quality_slider.get()) if hasattr(
                    self, 'quality_slider') else 85

                # Handle resize if enabled
                if self.resize_var.get():
                    try:
                        width = int(self.width_var.get())
                        height = int(self.height_var.get())

                        if self.keep_aspect_var.get():
                            # Maintain aspect ratio
                            img.thumbnail((width, height),
                                          Image.Resampling.LANCZOS)
                        else:
                            # Stretch to exact dimensions
                            img = img.resize(
                                (width, height), Image.Resampling.LANCZOS)
                    except (ValueError, AttributeError):
                        pass  # Skip resize if invalid dimensions

                # Convert based on format
                if format_name.upper() == 'JPEG':
                    if img.mode in ('RGBA', 'LA'):
                        # Convert to RGB for JPEG
                        background = Image.new(
                            'RGB', img.size, (255, 255, 255))
                        if img.mode == 'RGBA':
                            background.paste(img, mask=img.split()[3])
                        else:
                            background.paste(img, mask=img.split()[1])
                        img = background
                    img.save(dest_path, 'JPEG', quality=quality, optimize=True)
                elif format_name.upper() == 'PNG':
                    img.save(dest_path, 'PNG', optimize=True)
                elif format_name.upper() == 'WEBP':
                    img.save(dest_path, 'WEBP', quality=quality)
                else:
                    img.save(dest_path, format_name.upper())

                return True
        except Exception as e:
            logging.error(f"Error converting {src_path}: {e}")
            return False

    def is_image_file(self, file_path):
        """Check if file is an image"""
        image_extensions = {'.jpg', '.jpeg', '.png',
                            '.gif', '.bmp', '.tif', '.tiff', '.webp'}
        return file_path.suffix.lower() in image_extensions

    def rename_files(self):
        """Execute rename operation with image conversion support"""
        if not self.preview_data:
            messagebox.showwarning("Warning", "No operations to perform")
            return

        # Confirm operation
        if not messagebox.askyesno("Confirm", f"Rename {len(self.preview_data)} files?"):
            return

        success_count = 0
        error_count = 0
        converted_count = 0
        undo_operations = []

        # Get conversion settings
        convert_images = HAS_PIL and hasattr(
            self, 'convert_check') and self.convert_check.get()
        target_format = self.convert_format.get()

        try:
            for i, item in enumerate(self.preview_data):
                try:
                    original_path = item["original_path"]
                    new_path = item["new_path"]

                    # Check for conflicts
                    if new_path.exists() and new_path != original_path:
                        item["status"] = "Target exists"
                        self.tree.set(self.tree.get_children()
                                      [i], "status", "Skipped")
                        error_count += 1
                        continue

                    # Handle image conversion
                    if convert_images and self.is_image_file(original_path):
                        # Get target extension
                        target_ext = self.IMAGE_CONVERSION_FORMATS[target_format]['ext']
                        converted_path = new_path.with_suffix(target_ext)

                        if self.convert_image(original_path, converted_path, target_format):
                            # Store undo information
                            undo_operations.append({
                                'type': 'convert',
                                'original_path': str(original_path),
                                'new_path': str(converted_path)
                            })

                            # Remove original if not keeping it
                            if not self.keep_original.get():
                                original_path.unlink()

                            item["status"] = "Converted"
                            self.tree.set(self.tree.get_children()[
                                          i], "status", "✓✓")
                            converted_count += 1
                            success_count += 1
                        else:
                            item["status"] = "Conversion failed"
                            self.tree.set(self.tree.get_children()[
                                          i], "status", "Error")
                            error_count += 1
                    else:
                        # Regular rename
                        if original_path != new_path:
                            original_path.rename(new_path)

                            # Store undo information
                            undo_operations.append({
                                'type': 'rename',
                                'original_path': str(original_path),
                                'new_path': str(new_path)
                            })

                            item["status"] = "Renamed"
                            self.tree.set(self.tree.get_children()[
                                          i], "status", "✓")
                            success_count += 1
                        else:
                            item["status"] = "No change"
                            self.tree.set(self.tree.get_children()[
                                          i], "status", "-")

                except Exception as e:
                    logging.error(f"Error processing {item['original']}: {e}")
                    item["status"] = f"Error: {str(e)[:50]}"
                    self.tree.set(self.tree.get_children()
                                  [i], "status", "Error")
                    error_count += 1

            # Store undo data if operations were successful
            if undo_operations:
                self.undo_stack.append({
                    'timestamp': datetime.now().isoformat(),
                    'operations': undo_operations,
                    'description': f"Renamed {success_count} files"
                })
                self.undo_btn.configure(state="normal")

            # Update statistics
            self.stats['operations_count'] += 1
            self.update_stats()

            # Show results
            if error_count == 0:
                msg = f"Successfully processed {success_count} files"
                if converted_count > 0:
                    msg += f" ({converted_count} converted)"
                messagebox.showinfo("Success", msg)
            else:
                msg = f"Processed {success_count} files, {error_count} errors occurred"
                if converted_count > 0:
                    msg += f" ({converted_count} converted)"
                messagebox.showwarning("Completed with errors", msg)

            # Update status
            status_parts = []
            if success_count > 0:
                status_parts.append(f"{success_count} files processed")
            if converted_count > 0:
                status_parts.append(f"{converted_count} converted")
            if error_count > 0:
                status_parts.append(f"{error_count} errors")

            self.status_var.set(" | ".join(status_parts)
                                if status_parts else "Operation completed")

            # Disable rename button
            self.rename_btn.configure(state="disabled")

        except Exception as e:
            logging.error(f"Unexpected error during processing: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def undo_operation(self):
        """Undo the last rename operation"""
        if not self.undo_stack:
            messagebox.showinfo("Info", "No operations to undo")
            return

        last_operation = self.undo_stack.pop()
        success_count = 0
        error_count = 0

        try:
            for item in last_operation['operations']:
                try:
                    new_path = Path(item['new_path'])
                    original_path = Path(item['original_path'])

                    if new_path.exists():
                        new_path.rename(original_path)
                        success_count += 1
                    else:
                        error_count += 1
                        logging.warning(f"File not found for undo: {new_path}")

                except Exception as e:
                    error_count += 1
                    logging.error(f"Error undoing rename: {e}")

            if error_count == 0:
                messagebox.showinfo(
                    "Success", f"Successfully undid {success_count} operations")
            else:
                messagebox.showwarning("Partial Success",
                                       f"Undid {success_count} operations, {error_count} failed")

            # Update stats
            self.stats['operations_count'] = max(
                0, self.stats['operations_count'] - 1)
            self.update_stats()

            # Disable undo button if no more operations
            if not self.undo_stack:
                self.undo_btn.configure(state="disabled")

            # Refresh file list
            self.load_files()

        except Exception as e:
            messagebox.showerror("Error", f"Could not undo operation: {e}")

    def open_current_folder(self):
        """Open current folder in file explorer"""
        try:
            os.startfile(str(self.current_directory))
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")

    def save_settings(self):
        """Save current settings to file"""
        settings = {
            'directory': str(self.current_directory),
            'preset': self.selected_preset.get(),
            'pattern': self.pattern_entry.get(),
            'rename_pattern': self.rename_pattern.get(),
            'start_number': self.start_number.get(),
            'convert_format': self.convert_format.get(),
            'recursive': self.recursive_search.get(),
            'case_sensitive': self.case_sensitive.get()
        }

        if HAS_PIL and hasattr(self, 'quality_slider'):
            settings['quality'] = self.quality_slider.get()

        try:
            with open('quickrenaming_settings.json', 'w') as f:
                json.dump(settings, f, indent=2)
            messagebox.showinfo("Success", "Settings saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save settings: {e}")

    def load_settings(self):
        """Load settings from file"""
        try:
            with open('quickrenaming_settings.json', 'r') as f:
                settings = json.load(f)

            if 'directory' in settings and Path(settings['directory']).exists():
                self.current_directory = Path(settings['directory'])
                self.dir_entry.delete(0, 'end')
                self.dir_entry.insert(0, str(self.current_directory))

            if 'preset' in settings:
                self.selected_preset.set(settings['preset'])

            if 'pattern' in settings:
                self.pattern_entry.delete(0, 'end')
                self.pattern_entry.insert(0, settings['pattern'])

            if 'rename_pattern' in settings:
                self.rename_pattern.set(settings['rename_pattern'])

            if 'start_number' in settings:
                self.start_number.set(settings['start_number'])

            if 'convert_format' in settings:
                self.convert_format.set(settings['convert_format'])

            if 'quality' in settings and HAS_PIL and hasattr(self, 'quality_slider'):
                self.quality_slider.set(settings['quality'])

            if 'recursive' in settings:
                self.recursive_search.set(settings['recursive'])

            if 'case_sensitive' in settings:
                self.case_sensitive.set(settings['case_sensitive'])

        except FileNotFoundError:
            pass  # Settings file doesn't exist yet
        except Exception as e:
            logging.warning(f"Could not load settings: {e}")

    def export_file_list(self):
        """Export current file list to CSV"""
        if not self.filtered_files:
            messagebox.showwarning("Warning", "No files to export")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filename:
            try:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        ["Original Name", "Full Path", "Size", "Modified"])

                    for file_path in self.filtered_files:
                        try:
                            stat = file_path.stat()
                            writer.writerow([
                                file_path.name,
                                str(file_path),
                                stat.st_size,
                                datetime.fromtimestamp(
                                    stat.st_mtime).isoformat()
                            ])
                        except OSError:
                            continue

                messagebox.showinfo(
                    "Success", f"File list exported to {filename}")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Could not export file list: {e}")

    def refresh_files(self):
        """Refresh the current file list"""
        self.load_files()

    def clear_list(self):
        """Clear the file list and reset state"""
        self.tree.delete(*self.tree.get_children())
        self.files = []
        self.filtered_files = []
        self.preview_data = []
        self.rename_btn.configure(state="disabled")
        self.status_var.set("Ready")
        self.update_stats()
        self.file_count_label.configure(text="0 files")

    def show_about(self):
        """Show about dialog"""
        about_text = """QuickRenaming Pro v1.0.6

Developer: Dimona Patrick
Organization: Dream-Pixels-Forge
License: GNU General Public License

Advanced file renaming and image conversion tool
with modern bento grid interface.

Features:
• Batch file renaming with patterns
• Image format conversion (JPEG, PNG, WEBP, etc.)
• Image resizing with quality control
• Advanced filtering and search
• Undo operations
• Statistics and export capabilities"""
        
        messagebox.showinfo("About QuickRenaming Pro", about_text)

    def on_closing(self):
        """Handle window close event with settings save"""
        try:
            self.save_settings()
        except:
            pass  # Don't block closing if settings save fails

        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.root.destroy()


def main():
    root = ctk.CTk()
    app = QuickRenamingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
