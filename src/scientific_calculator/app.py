from __future__ import annotations

import copy
import logging
import math
import multiprocessing
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from contextlib import suppress
from logging.handlers import RotatingFileHandler
from tkinter import messagebox, simpledialog, ttk

import numpy as np
import sympy as sp
from PIL import Image, ImageTk

from .calculation_controller import CalculationController
from .calculation_errors import CalculationTimeout
from .calculator_engine import (
    CONSTANTS_DATASET_LABELS,
    CONVERSIONS,
    CalculatorError,
    ScientificCalculatorEngine,
    constants_for_dataset,
)
from .errors import translate_error_message
from .restart_manager import restart_application
from .settings_store import SettingsStore
from .spreadsheet import SpreadsheetModel

LOGGER = logging.getLogger("scientific_calculator")


class App(tk.Tk):
    MODES=["Calculate","Complex","Base-N","Matrix","Vector","Statistics","Distribution","Spreadsheet","Table","Equation/Func","Inequality","Ratio"]
    LCD_WORKSPACE_MODES=frozenset({
        "Matrix", "Vector", "Statistics", "Distribution", "Spreadsheet",
        "Table", "Equation/Func", "Inequality", "Ratio",
    })
    MODE_HINTS={
        "Calculate":"Enter expression, then =",
        "Complex":"Enter z, then =",
        "Base-N":"Select base, enter value, =",
        "Matrix":"LCD form: OPTN action, = next",
        "Vector":"LCD form: OPTN action, = next",
        "Statistics":"LCD form: choose analysis, = next",
        "Distribution":"LCD form: choose distribution, = next",
        "Spreadsheet":"LCD cells: arrows move, = save",
        "Table":"LCD form: f(x), range, then =",
        "Equation/Func":"LCD form: choose equation type",
        "Inequality":"LCD form: degree, coefficients, relation",
        "Ratio":"LCD form: choose ratio type",
    }
    ALPHA_MAP={"neg":"A","dms":"B","inv":"C","sin":"D","cos":"E","tan":"F","rparen":"x","sd":"y","mplus":"M","sci":"e"}
    UI_SCALES=(25,50,75,100,125,150,200)
    SKINS={
        "Graphite":"skins/skin_graphite.png",
        "Blue":"skins/skin_blue.png",
        "Pink":"skins/skin_pink.png",
        "White":"skins/skin_white.png",
    }
    BOOLEAN_SETTINGS=frozenset({
        "engineer_symbol", "statistics_freq", "spreadsheet_auto_calc",
        "equation_complex", "digit_separator",
    })
    # Physical keyboard input is deliberately narrower than the parser.  A
    # keyboard must not become a hidden second input language: every accepted
    # character maps to a visible calculator key or one of its SHIFT/ALPHA
    # functions.  Functions such as sin() and sqrt() are inserted by their
    # dedicated calculator keys rather than typed letter by letter.
    KEYBOARD_CHARACTER_MAP={
        "*":"×", "-":"−", "+":"+", "/":"/", "^":"^",
        "(":"(", ")":")", ",":",", ".":".", "%":"%", "=":"=",
        "×":"×", "−":"−", "÷":"/", "π":"π",
    }
    KEYBOARD_VARIABLES=frozenset({"A", "B", "C", "D", "E", "F", "M", "d", "t", "u", "v", "x", "y", "z", "e"})
    SETTINGS_DATA_VERSION=3
    SETTINGS_SCHEMA_VERSION=SETTINGS_DATA_VERSION  # compatibility with saved v1/v2 payloads
    SETTINGS_ENUMS={
        "angle_unit":frozenset({"DEG","RAD","GRA"}),
        "input_output":frozenset({"MathI/MathO","MathI/DecimalO","LineI/LineO","LineI/DecimalO"}),
        "number_format":frozenset({"Norm","Fix","Sci"}),
        "fraction_result":frozenset({"d/c","a b/c"}),
        "complex_format":frozenset({"a+bi","r∠θ"}),
        "spreadsheet_show_cell":frozenset({"Formula","Value"}),
        "decimal_mark":frozenset({"Dot","Comma"}),
        "multiline_font":frozenset({"Normal","Small"}),
        "constant_dataset":frozenset(CONSTANTS_DATASET_LABELS),
    }
    LCD_TEXT_COLOR="#273026"
    def __init__(self):
        super().__init__()
        try:
            self._tk_pixels_per_point = float(self.tk.call("tk", "scaling"))
        except Exception:
            self._tk_pixels_per_point = 96.0 / 72.0
        self.title("Scientific Calculator")
        self.skin_mode=True
        self.load_settings_file()
        self.ui_scale=self._fit_ui_scale_to_display(self.ui_scale)
        self.geometry(f"{self._sp(480)}x{self._sp(980)}")
        self.resizable(False,False)
        self.configure(bg="#ffffff")
        with suppress(Exception):
            self.iconbitmap(self._resource_path("icons/app.ico"))
        self.core=ScientificCalculatorEngine(); self.sheet=SpreadsheetModel(self.core)
        self.apply_saved_engine_settings()
        self.load_calculation_history()
        self.mode="Calculate"; self.shift=False; self.alpha=False; self.base=10; self.history_pos=max(0,len(self.core.history)-1); self.undo=[]; self.overwrite=False
        self._calculation_busy=False
        self.calculation_controller=CalculationController(self)
        self._lcd_flow=None
        self.template_kind=None; self.template_fields={}; self.template_order=[]; self.template_index=0; self.template_cursors={}; self._template_rendering=False
        self._ui(); self.status_refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)


    def _db_base_path(self):
        """Persistent local SQLite settings database."""
        root = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".scientific_calculator")
        # Keep path discovery side-effect free.  ``SettingsStore.load`` owns
        # directory creation and safely falls back to in-memory defaults when
        # a profile directory is unavailable (for example, read-only).
        return os.path.join(root, "ScientificCalculator", "settings.db")

    @staticmethod
    def _default_saved_config():
        return {"schema_version":App.SETTINGS_DATA_VERSION, "scale":100, "skin":"Graphite", "calculator_settings":{}}

    def _log_settings_issue(self, operation, error):
        """Record only an operation and error class; never persist setting values."""
        try:
            log_path=os.path.join(os.path.dirname(self._db_base_path()),"settings.log")
            logger=logging.getLogger("scientific_calculator.settings")
            logger.setLevel(logging.WARNING)
            if not any(getattr(handler,"baseFilename",None)==os.path.abspath(log_path) for handler in logger.handlers):
                handler=RotatingFileHandler(log_path,maxBytes=64*1024,backupCount=1,encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                logger.addHandler(handler)
            logger.warning("settings_%s_failed error=%s",operation,type(error).__name__)
        except Exception:
            # The calculator must still start when a disk/permission problem
            # prevents diagnostic logging.
            pass

    @classmethod
    def _sanitize_calculator_settings(cls, saved):
        if not isinstance(saved,dict):
            return {}
        clean={}
        for name,value in saved.items():
            if name in cls.BOOLEAN_SETTINGS:
                try:
                    clean[name]=cls._coerce_boolean_setting(name,value)
                except ValueError:
                    continue
            elif name=="table_two_functions":
                if type(value) is bool:
                    clean[name]=value
            elif name=="number_digits":
                if type(value) is int and 0<=value<=9:
                    clean[name]=value
            elif name in cls.SETTINGS_ENUMS and value in cls.SETTINGS_ENUMS[name]:
                clean[name]=value
        return clean

    @classmethod
    def _sanitize_saved_config(cls, saved):
        clean=cls._default_saved_config()
        if not isinstance(saved,dict):
            return clean
        clean["scale"]=cls._validated_ui_scale(saved.get("scale",100))
        clean["skin"]=cls._validated_skin_name(saved.get("skin","Graphite"))
        clean["calculator_settings"]=cls._sanitize_calculator_settings(saved.get("calculator_settings",{}))
        return clean

    @classmethod
    def _migrate_settings(cls, saved):
        """Validate the plain, typed data reconstructed from SQLite."""
        if not isinstance(saved,dict):
            return None
        version=saved.get("schema_version",1)
        if type(version) is not int or version < 1 or version > cls.SETTINGS_DATA_VERSION:
            return None
        payload=dict(saved)
        if version < cls.SETTINGS_DATA_VERSION:
            # New schema revisions retain valid typed values and use defaults
            # for newly introduced options such as the CODATA catalogue.
            payload["schema_version"]=cls.SETTINGS_DATA_VERSION
        return payload

    def _settings_store(self):
        return SettingsStore(self._db_base_path(), self._log_settings_issue)

    @staticmethod
    def _flatten_settings(data):
        flat = {
            "schema_version": data["schema_version"],
            "scale": data["scale"],
            "skin": data["skin"],
        }
        flat.update({f"calculator.{key}": value for key, value in data["calculator_settings"].items()})
        return flat

    @staticmethod
    def _unflatten_settings(data):
        if not isinstance(data, dict):
            return None
        settings = {key.removeprefix("calculator."): value for key, value in data.items() if key.startswith("calculator.")}
        return {
            "schema_version": data.get("schema_version", App.SETTINGS_DATA_VERSION),
            "scale": data.get("scale", 100),
            "skin": data.get("skin", "Graphite"),
            "calculator_settings": settings,
        }

    def load_settings_file(self):
        saved = self._settings_store().load()
        cfg=self._sanitize_saved_config(self._migrate_settings(self._unflatten_settings(saved)))
        self.saved_config = cfg
        self.ui_scale = self._validated_ui_scale(cfg.get("scale",100))
        self.skin_name = self._validated_skin_name(cfg.get("skin","Graphite"))

    @classmethod
    def _validated_ui_scale(cls, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return 100
        return value if value in cls.UI_SCALES else 100

    @classmethod
    def _validated_skin_name(cls, value):
        """Return a bundled skin name, falling back safely for old/corrupt settings."""
        return value if value in cls.SKINS else "Graphite"

    def apply_saved_engine_settings(self):
        saved=self._sanitize_calculator_settings(getattr(self,"saved_config",{}).get("calculator_settings",{}))
        for k,v in saved.items():
            if hasattr(self.core.settings,k):
                setattr(self.core.settings,k,v)

    def _history_entries(self):
        entries=[]
        for entry in getattr(self.core,"history",[]):
            if isinstance(entry,(list,tuple)) and len(entry)==2 and all(isinstance(value,str) for value in entry):
                entries.append((entry[0],entry[1]))
        return entries[-SettingsStore.HISTORY_LIMIT:]

    def load_calculation_history(self):
        try:
            entries=self._settings_store().load_history()
            self.core.history[:]=entries or []
        except Exception as error:
            self._log_settings_issue("load history",error)
            self.core.history[:]=[]

    def _persist_calculation_history(self, store=None):
        entries=self._history_entries()
        self.core.history[:]=entries
        (store or self._settings_store()).save_history(entries)
        self.history_pos=max(0,len(entries)-1)
        return entries

    def _lcd_message(self, message):
        """Show a short status on the calculator itself when it is available."""
        with suppress(AttributeError, RecursionError, tk.TclError):
            self.result.config(text=self._lcd_clip(message))

    @classmethod
    def _coerce_boolean_setting(cls, name, value):
        """Normalize Setup/persisted On/Off values without truthy string leakage."""
        if name not in cls.BOOLEAN_SETTINGS:
            return value
        if isinstance(value,bool):
            return value
        if value=="On":
            return True
        if value=="Off":
            return False
        raise ValueError(f"Invalid boolean setting: {name}")

    def save_settings_file(self, notify=False):
        data = {
            "schema_version": self.SETTINGS_DATA_VERSION,
            "scale": self._validated_ui_scale(getattr(self,"ui_scale",100)),
            "skin": self._validated_skin_name(getattr(self,"skin_name","Graphite")),
            "calculator_settings": self._sanitize_calculator_settings(dict(vars(self.core.settings))) if hasattr(self,"core") else {}
        }
        try:
            store = self._settings_store()
            history=self._history_entries()
            self.core.history[:]=history
            store.save_state(self._flatten_settings(data), history)
            if self._sanitize_saved_config(self._migrate_settings(self._unflatten_settings(store.load()))) != data:
                raise OSError("settings verification failed")
            if store.load_history() != history:
                raise OSError("history verification failed")
            self.saved_config = data
            if notify:
                self._lcd_message("Settings saved")
            return True
        except Exception as e:
            self._log_settings_issue("save",e)
            if notify:
                self.err(CalculatorError("Settings ERROR: save failed"), clear_input=False)
            return False

    def _rebuild_scaled_ui(self):
        expression = ""
        result_text = "0"
        cursor = 0
        try:
            expression = self.expr.get()
            result_text = self.result.cget("text")
            cursor = self.expr.index(tk.INSERT)
        except (AttributeError, tk.TclError):
            pass
        template_active = bool(getattr(self,"template_kind",None))
        for child in self.winfo_children():
            # Auxiliary mode windows retain their work when the calculator skin
            # is rebuilt for a new UI scale.  Only root UI widgets belong to
            # the scaled canvas and should be recreated here.
            if not isinstance(child,tk.Toplevel):
                child.destroy()
        # Windows keeps a non-resizable Tk window at its previous dimensions.
        # Temporarily unlock it so every supported scale gets its own geometry.
        self.resizable(True,True)
        try:
            self.geometry(f"{self._sp(480)}x{self._sp(980)}")
            self._ui()
            if template_active:
                self.result.config(text=result_text)
                self.render_template()
            else:
                self.set_expr(expression)
                self.result.config(text=result_text)
                self.expr.icursor(max(0,min(len(expression),cursor)))
            self.status_refresh()
        finally:
            self.resizable(False,False)

    def apply_scale(self, percent):
        self.ui_scale = self._fit_ui_scale_to_display(percent)
        self.save_settings_file(False)
        self._rebuild_scaled_ui()

    def reset_app_settings(self):
        try:
            self._settings_store().reset_defaults()
        except Exception as error:
            self._log_settings_issue("reset", error)
            self.err(CalculatorError("Settings ERROR: reset failed"), clear_input=False)
            return False
        self.ui_scale = 100
        self.skin_name = "Graphite"
        try:
            self.core.settings = type(self.core.settings)()
            self.core.history.clear()
            self.history_pos=0
        except Exception:
            pass
        self.saved_config = self._default_saved_config()
        self._rebuild_scaled_ui()
        self._lcd_message("Settings reset")
        return True

    def clear_calculation_history(self):
        """Remove only calculation history and persist the change atomically."""
        previous_history=list(self.core.history)
        previous_position=getattr(self,"history_pos",0)
        self.core.history.clear()
        self.history_pos=0
        if self.save_settings_file(False):
            self._lcd_message("History cleared")
            return True
        self.core.history[:]=previous_history
        self.history_pos=previous_position
        self.err(CalculatorError("Settings ERROR: history clear failed"), clear_input=False)
        return False

    def _run_background_calculation(self, method, args, on_success):
        """Run an engine method in a cancellable isolated process.

        The worker receives a snapshot. Its Ans/history/memory changes are
        committed only by this Tk-thread callback, after its operation id has
        been confirmed by the controller.
        """
        def start():
            self._calculation_busy=True
            self.result.config(text="Calculating…")

        def success(payload):
            self.core.ans = payload.ans
            self.core.history[:] = payload.history
            self.core.memory.clear(); self.core.memory.update(payload.memory)
            on_success(payload.result)
            try:
                self._persist_calculation_history()
            except Exception as error:
                self._log_settings_issue("save history",error)

        def failure(error): self.err(error)
        def finish(): self._calculation_busy=False
        try:
            return self.calculation_controller.start_engine_method(
                self.core, method, *args, on_start=start, on_success=success,
                on_error=failure, on_finish=finish,
            )
        except Exception as error:
            self.err(error)
            return False

    def _on_close(self):
        # Persist the current Setup state even if the user closes the app later.
        try:
            controller = self.__dict__.get("calculation_controller")
            if controller: controller.close()
            self.save_settings_file(False)
        finally:
            self.destroy()

    def _resource_path(self,name):
        frozen_base=getattr(sys,"_MEIPASS",None)
        if frozen_base:
            return os.path.join(frozen_base,name)
        here=os.path.dirname(os.path.abspath(__file__))
        project_asset=os.path.abspath(os.path.join(here,"..","..","assets",name))
        if os.path.exists(project_asset):
            return project_asset
        return os.path.join(here,name)

    def _skin_xy(self,x,y):
        # Original generated-image coordinates -> current scaled skin coordinates.
        base_x=(float(x)-330.0)*0.8
        base_y=(float(y)-5.0)*0.8
        return (int(round(base_x*self._scale_factor())),
                int(round(base_y*self._scale_factor())))


    def _scale_factor(self):
        return self.ui_scale / 100.0

    def _fit_ui_scale_to_display(self, requested_scale):
        """Keep the full calculator visible on macOS rather than crop its Canvas.

        macOS Tk reports logical points on Retina displays. When a selected
        calculator scale is taller than that work area, the window manager can
        clip the Canvas instead of shrinking it. On macOS choose the largest
        supported scale that fits; Windows and Linux retain the user's choice.
        """
        requested_scale=self._validated_ui_scale(requested_scale)
        if sys.platform!="darwin":
            return requested_scale
        try:
            available_width=max(1,self.winfo_screenwidth()-24)
            available_height=max(1,self.winfo_screenheight()-96)
            maximum=int(math.floor(100*min(available_width/480,available_height/980)))
        except (AttributeError, RecursionError, tk.TclError):
            return requested_scale
        choices=[scale for scale in self.UI_SCALES if scale<=maximum]
        return min(requested_scale,max(choices,default=self.UI_SCALES[0]))

    def _sp(self,v):
        """Scale a 100%-reference pixel coordinate with consistent rounding."""
        return max(0,int(round(float(v) * self._scale_factor())))

    def _fp(self,base_points):
        """Return a negative Tk font size (pixels), preserving the 100% look exactly."""
        px_at_100 = float(base_points) * self._tk_pixels_per_point
        px = max(1,int(round(px_at_100 * self._scale_factor())))
        return -px

    def _fs(self,v):
        """Legacy point-size helper for non-LCD UI only."""
        return max(1,int(round(float(v) * self._scale_factor())))

    @staticmethod
    def _table_row_count(start, end, step, two_functions=False):
        try:
            start=float(start); end=float(end); step=float(step)
        except (TypeError, ValueError) as exc:
            raise CalculatorError("Range ERROR") from exc
        if not all(math.isfinite(v) for v in (start,end,step)) or step==0:
            raise CalculatorError("Range ERROR")
        span=(end-start)/step
        if not math.isfinite(span):
            raise CalculatorError("Range ERROR")
        if span<0:
            raise CalculatorError("Range ERROR: adım yönü başlangıç/bitiş ile uyuşmuyor")
        count=int(math.floor(span+1e-12))+1
        limit=30 if two_functions else 45
        if count<1 or count>limit:
            raise CalculatorError("Range ERROR")
        return count


    def _add_hotspot(self,name,box,cmd):
        x1,y1=self._skin_xy(box[0],box[1]); x2,y2=self._skin_xy(box[2],box[3])
        self.skin_hotspots.append((name,x1,y1,x2,y2,cmd))

    def _skin_click(self,event):
        for name,x1,y1,x2,y2,cmd in reversed(self.skin_hotspots):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if self.__dict__.get("_calculation_busy",False) and name != "AC":
                    return "break"
                cmd()
                return "break"

    def _refresh_modifier_status(self):
        """Show modifier state as colored LCD text only."""
        try:
            self.shift_status.config(text="SHIFT" if self.shift else "")
            self.alpha_status.config(text="ALPHA" if self.alpha else "")
        except (AttributeError, tk.TclError):
            pass

    def _ui(self):
        # The selected calculator skin is the visual layout reference.
        self.skin_canvas=tk.Canvas(self,width=self._sp(480),height=self._sp(980),bg="#ffffff",
                                   highlightthickness=0,bd=0)
        self.skin_canvas.pack(fill="both",expand=False)
        skin_file=self.SKINS[self._validated_skin_name(getattr(self,"skin_name","Graphite"))]
        base_skin=Image.open(self._resource_path(skin_file))
        target_size=(self._sp(480),self._sp(980))
        if base_skin.size != target_size:
            base_skin=base_skin.resize(target_size,Image.LANCZOS)
        self._skin_img=ImageTk.PhotoImage(base_skin)
        self.skin_canvas.create_image(0,0,image=self._skin_img,anchor="nw")

        # Dynamic LCD overlay: cover the static spreadsheet screenshot only inside screen.
        sx1,sy1=self._sp(40),self._sp(128)
        sx2,sy2=self._sp(435),self._sp(289)
        self.skin_canvas.create_rectangle(sx1,sy1,sx2,sy2,fill="#eaf0e5",outline="#111111",width=max(1,self._sp(1)))

        status_x=sx1+self._sp(7); status_y=sy1+self._sp(7)
        status_width=(sx2-sx1)-self._sp(14)
        modifier_width=self._sp(105)
        self.status=tk.Label(self.skin_canvas,text="",font=("Consolas",self._fp(9),"bold"),
                             anchor="w",bg="#eaf0e5",fg="#273026")
        self.status.place(x=status_x,y=status_y,width=max(0,status_width-modifier_width),height=self._sp(20))
        self.shift_status=tk.Label(self.skin_canvas,text="",font=("Consolas",self._fp(9),"bold"),
                                   anchor="e",bg="#eaf0e5",fg=self.LCD_TEXT_COLOR)
        self.shift_status.place(x=status_x+status_width-self._sp(105),y=status_y,
                                width=self._sp(49),height=self._sp(20))
        self.alpha_status=tk.Label(self.skin_canvas,text="",font=("Consolas",self._fp(9),"bold"),
                                   anchor="e",bg="#eaf0e5",fg=self.LCD_TEXT_COLOR)
        self.alpha_status.place(x=status_x+status_width-self._sp(54),y=status_y,
                                width=self._sp(54),height=self._sp(20))

        self.expr=tk.Entry(self.skin_canvas,font=("Consolas",self._fp(19)),justify="right",
                           bg="#f0f4ed",fg="#111111",insertbackground="#111111",
                           insertwidth=max(1,self._sp(2)),relief="flat",bd=0)
        self.expr.place(x=sx1+self._sp(7),y=sy1+self._sp(34),width=(sx2-sx1)-self._sp(14),height=self._sp(51))

        self.template_canvas=tk.Canvas(self.skin_canvas,bg="#f0f4ed",
                                       highlightthickness=0,bd=0)
        self.template_canvas.bind("<KeyPress>",self._template_keypress)

        self.result=tk.Label(self.skin_canvas,text="0",font=("Consolas",self._fp(18),"bold"),
                             anchor="e",bg="#f0f4ed",fg="#111111")
        self.result.place(x=sx1+self._sp(7),y=sy1+self._sp(89),width=(sx2-sx1)-self._sp(14),height=self._sp(58))

        self.expr.bind("<KeyPress>",self._physical_keypress)
        self.expr.bind("<KeyPress>",self._template_keypress,add="+")
        self.expr.bind("<KeyPress>",self._lcd_keypress,add="+")

        self.skin_hotspots=[]

        # Top controls
        self._add_hotspot("SHIFT",(375,430,425,482),self.shift_key)
        self._add_hotspot("ALPHA",(452,430,504,482),self.alpha_key)
        self._add_hotspot("MENU",(742,430,792,482),self.menu_key)
        self._add_hotspot("ON",(820,430,872,482),self.on_key)

        # Direction pad
        self._add_hotspot("UP",(589,429,656,477),lambda:self.vertical_move(-1))
        self._add_hotspot("LEFT",(526,470,586,530),lambda:self.move(-1))
        self._add_hotspot("RIGHT",(659,470,720,530),lambda:self.move(1))
        self._add_hotspot("DOWN",(589,522,656,570),lambda:self.vertical_move(1))

        # Function top row
        self._add_hotspot("OPTN",(363,536,438,585),self.optn_key)
        self._add_hotspot("CALC",(451,536,526,585),self.calc_key)
        self._add_hotspot("INTEGRAL",(720,536,785,585),self.integral_key)
        self._add_hotspot("X",(808,536,873,585),self.x_key)

        # Scientific rows
        self._add_hotspot("FRACTION",(363,610,437,660),self.fraction_key)
        self._add_hotspot("SQRT",(451,610,525,660),self.sqrt_key)
        self._add_hotspot("SQUARE",(540,610,614,660),self.square_key)
        self._add_hotspot("POWER",(628,610,703,660),self.power_key)
        self._add_hotspot("LOG",(716,610,792,660),self.log_key)
        self._add_hotspot("LN",(805,610,879,660),self.ln_key)

        self._add_hotspot("NEG",(363,683,437,733),self.neg_key)
        self._add_hotspot("DMS",(451,683,525,733),self.dms_key)
        self._add_hotspot("INV",(540,683,614,733),self.inv_key)
        self._add_hotspot("SIN",(628,683,703,733),lambda:self.trig_key("sin"))
        self._add_hotspot("COS",(716,683,792,733),lambda:self.trig_key("cos"))
        self._add_hotspot("TAN",(805,683,879,733),lambda:self.trig_key("tan"))

        self._add_hotspot("STO",(363,754,437,807),self.sto_key)
        self._add_hotspot("ENG",(451,754,525,807),self.eng_key)
        self._add_hotspot("LPAREN",(540,754,614,807),self.lparen_key)
        self._add_hotspot("RPAREN",(628,754,703,807),self.rparen_key)
        self._add_hotspot("SD",(716,754,792,807),self.sd_key)
        self._add_hotspot("MPLUS",(805,754,879,807),self.mplus_key)

        # Numeric keypad
        self._add_hotspot("7",(363,832,456,902),lambda:self.num_key("7"))
        self._add_hotspot("8",(468,832,561,902),lambda:self.num_key("8"))
        self._add_hotspot("9",(574,832,667,902),lambda:self.num_key("9"))
        self._add_hotspot("DEL",(680,832,773,902),self.del_key)
        self._add_hotspot("AC",(786,832,879,902),self.ac_key)

        self._add_hotspot("4",(363,918,456,987),lambda:self.num_key("4"))
        self._add_hotspot("5",(468,918,561,987),lambda:self.num_key("5"))
        self._add_hotspot("6",(574,918,667,987),lambda:self.num_key("6"))
        self._add_hotspot("MUL",(680,918,773,987),self.mul_key)
        self._add_hotspot("DIV",(786,918,879,987),self.div_key)

        self._add_hotspot("1",(363,1002,456,1073),lambda:self.num_key("1"))
        self._add_hotspot("2",(468,1002,561,1073),lambda:self.num_key("2"))
        self._add_hotspot("3",(574,1002,667,1073),lambda:self.num_key("3"))
        self._add_hotspot("PLUS",(680,1002,773,1073),self.plus_key)
        self._add_hotspot("MINUS",(786,1002,879,1073),self.minus_key)

        self._add_hotspot("0",(363,1088,456,1158),lambda:self.num_key("0"))
        self._add_hotspot("DOT",(468,1088,561,1158),self.dot_key)
        self._add_hotspot("SCI",(574,1088,667,1158),self.sci_key)
        self._add_hotspot("ANS",(680,1088,773,1158),self.ans_key)
        self._add_hotspot("EQUALS",(786,1088,879,1158),self.equals)

        self.skin_canvas.bind("<Button-1>",self._skin_click)
        self.bind("<F1>",lambda e:self.help_key())
        self.bind("<Escape>",lambda e:self.ac_key())
        self.expr.focus_set()

    def status_refresh(self):
        self.status.config(text=f"{self.mode}  {self.core.settings.angle_unit}  B{self.base}")
        self._refresh_modifier_status()

    @staticmethod
    def _lcd_clip(text,limit=28):
        text=str(text).replace("\n"," ")
        return text if len(text)<=limit else text[:max(1,limit-1)]+"…"

    @classmethod
    def _history_line(cls, expression, result):
        """Keep both the operation and its ``=`` result visible on the LCD."""
        result_text=cls._lcd_clip(result, 12)
        expression_limit=max(3, 28-len(result_text)-3)
        return f"{cls._lcd_clip(expression, expression_limit)} = {result_text}"

    @staticmethod
    def _lcd_title(title):
        """Keep flow guidance inside the deliberately compact calculator LCD."""
        first=str(title).split(maxsplit=1)[0].upper()
        return {
            "MATRIX":"MAT", "VECTOR":"VCT", "STATISTICS":"STAT",
            "DISTRIBUTION":"DIST", "SPREADSHEET":"SHEET", "TABLE":"TABLE",
            "EQUATION":"EQN", "INEQUALITY":"INEQ", "RATIO":"RATIO",
            "POLYNOMIAL":"POLY", "SIMULTANEOUS":"SIMUL",
        }.get(first,first[:8])

    def _format_error_message(self,e):
        return translate_error_message(e)

    def _lcd_flow_active(self):
        return self.__dict__.get("_lcd_flow") is not None

    def _history_lcd_active(self):
        flow=self.__dict__.get("_lcd_flow")
        return bool(flow and flow.get("mode")=="History")

    def _reset_lcd_flow(self):
        self._lcd_flow=None

    def _set_lcd_expression(self,text):
        self.expr.delete(0,tk.END)
        self.expr.insert(0,str(text))
        self.expr.icursor(tk.END)

    def _entry_vertical_key(self,direction):
        """Route keyboard ▲/▼ through the same context-sensitive LCD controls."""
        if self._lcd_flow_active() or self.template_kind:
            self.vertical_move(direction)
        else:
            self.history_move(direction)
        return "break"

    def _entry_horizontal_key(self,direction):
        """Only consume ◀/▶ when an LCD flow assigns them a navigation meaning."""
        if self._lcd_move(direction):
            return "break"
        return None

    def _lcd_prepare_direct_entry(self):
        """Replace a newly rendered field default on the first calculator-key press."""
        flow=self.__dict__.get("_lcd_flow")
        if not flow or flow.get("phase")!="form" or not flow.get("field_armed",False):
            return
        flow["field_armed"]=False
        self.expr.delete(0,tk.END)
        with suppress(tk.TclError):
            self.expr.selection_clear()

    def _lcd_error(self,e):
        flow=self.__dict__.get("_lcd_flow")
        if flow is None:
            self.err(e)
            return
        flow["last_error"]=self._format_error_message(e)
        self._clear_active_input_for_error()
        self._clear_modifiers()
        self.result.config(text=self._lcd_clip("ERROR: "+flow["last_error"]))

    def _lcd_real(self,text,label="value",integer=False,minimum=None,maximum=None):
        raw=str(text).strip()
        if not raw:
            raise CalculatorError(f"Argument ERROR: {label} is required")
        try:
            parsed=self.core.parse(raw)
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError(f"Argument ERROR: {label}") from exc
        result=self._lcd_real_expression(parsed,label)
        if integer:
            if not result.is_integer():
                raise CalculatorError(f"Argument ERROR: {label} must be an integer")
            result=int(result)
        if minimum is not None and result<minimum:
            raise CalculatorError(f"Argument ERROR: {label} must be at least {minimum}")
        if maximum is not None and result>maximum:
            raise CalculatorError(f"Argument ERROR: {label} must be at most {maximum}")
        return result

    @staticmethod
    def _lcd_real_expression(parsed,label="value"):
        if getattr(parsed,"free_symbols",set()):
            raise CalculatorError(f"Argument ERROR: {label} must be numeric")
        try:
            value=complex(sp.N(parsed,17))
        except Exception as exc:
            raise CalculatorError(f"Argument ERROR: {label}") from exc
        if abs(value.imag)>1e-12 or not math.isfinite(value.real):
            raise CalculatorError(f"Math ERROR: {label} must be finite and real")
        return float(value.real)

    def _lcd_numbers(self,text,label):
        values=[part for part in re.split(r"[ ,;\n]+",str(text).strip()) if part]
        if not values:
            raise CalculatorError(f"Argument ERROR: {label} is required")
        return [self._lcd_real(value,label) for value in values]

    def _lcd_function(self,text,label="function"):
        raw=str(text).strip()
        if not raw:
            raise CalculatorError(f"Argument ERROR: {label} is required")
        try:
            symbol=sp.Symbol("x")
            self.core.parse(raw,{"x":symbol})
        except CalculatorError:
            raise
        except Exception as exc:
            raise CalculatorError(f"Syntax ERROR: {label}") from exc
        return raw

    def _lcd_parse_field(self,spec,raw):
        kind=spec.get("type","text")
        label=spec.get("label",spec["key"])
        if kind=="number":
            return self._lcd_real(raw,label,minimum=spec.get("minimum"),maximum=spec.get("maximum"))
        if kind=="integer":
            return self._lcd_real(raw,label,integer=True,minimum=spec.get("minimum"),maximum=spec.get("maximum"))
        if kind=="numbers":
            return self._lcd_numbers(raw,label)
        if kind=="function":
            return self._lcd_function(raw,label)
        if kind=="choice":
            choice=self._lcd_real(raw,label,integer=True)
            if choice not in spec["choices"]:
                raise CalculatorError(f"Argument ERROR: choose one of {', '.join(map(str,spec['choices']))}")
            return spec["choices"][choice]
        if kind=="raw":
            return str(raw)
        return str(raw).strip()

    @staticmethod
    def _lcd_number_text(value):
        if isinstance(value,(int,np.integer)):
            return str(int(value))
        if isinstance(value,(float,np.floating)):
            return f"{float(value):.12g}"
        return str(value)

    def _lcd_field_text(self,flow,spec):
        key=spec["key"]
        if key in flow.get("draft",{}):
            return flow["draft"][key]
        if key in flow.get("values",{}):
            value=flow["values"][key]
            if spec.get("type")=="choice":
                for number,choice in spec["choices"].items():
                    if choice==value:
                        return str(number)
            return self._lcd_number_text(value)
        default=spec.get("default","")
        if spec.get("type")=="choice":
            for number,choice in spec["choices"].items():
                if choice==default:
                    return str(number)
        return self._lcd_number_text(default)

    def _lcd_current_spec(self):
        flow=self.__dict__.get("_lcd_flow")
        if not flow or flow.get("phase")!="form":
            return None
        fields=flow.get("fields",[])
        index=flow.get("index",0)
        return fields[index] if 0<=index<len(fields) else None

    def _lcd_begin_form(self,title,fields,stage):
        flow=self._lcd_flow
        flow.update({
            "phase":"form", "title":title, "fields":list(fields), "stage":stage,
            "index":0, "draft":{}, "result_lines":[], "result_index":0,
            "field_armed":False,
        })
        self._lcd_render_field()

    def _lcd_render_field(self):
        flow=self.__dict__.get("_lcd_flow")
        spec=self._lcd_current_spec()
        if not flow or spec is None:
            return
        self._set_lcd_expression(self._lcd_field_text(flow,spec))
        # Fresh defaults should be replaceable with one keypad press.  Native
        # keyboard input replaces the selection; ``insert`` handles skin keys.
        flow["field_armed"]=True
        self.expr.selection_range(0,tk.END)
        index=flow["index"]+1; total=len(flow["fields"])
        title=self._lcd_title(flow["title"])
        if spec.get("type")=="choice":
            try:
                selected=self._lcd_parse_field(spec,self.expr.get())
                selected_text=self._lcd_clip(selected,11)
            except Exception:
                selected_text="choose"
            prompt=f"{title} {index}/{total} {selected_text} ◀▶ ="
        else:
            prompt=f"{title} {index}/{total} {spec.get('label',spec['key'])} ="
        self.result.config(text=self._lcd_clip(prompt))
        self.expr.focus_set()

    def _lcd_capture_draft(self):
        flow=self.__dict__.get("_lcd_flow")
        spec=self._lcd_current_spec()
        if flow and spec is not None:
            flow.setdefault("draft",{})[spec["key"]]=self.expr.get()

    def _lcd_show_results(self,title,lines):
        flow=self._lcd_flow
        flow.update({"phase":"results","title":title,"result_lines":[str(line) for line in lines] or ["0"],"result_index":0})
        self._lcd_render_result()

    def _lcd_render_result(self):
        flow=self.__dict__.get("_lcd_flow")
        if not flow or flow.get("phase")!="results":
            return
        lines=flow.get("result_lines",["0"])
        flow["field_armed"]=False
        flow["result_index"]=max(0,min(len(lines)-1,flow.get("result_index",0)))
        index=flow["result_index"]
        self._set_lcd_expression(f"{self._lcd_title(flow['title'])} {index+1}/{len(lines)}  ▲▼  OPTN")
        self.result.config(text=self._lcd_clip(lines[index]))
        self.expr.focus_set()

    def _lcd_cycle_choice(self,direction):
        flow=self.__dict__.get("_lcd_flow")
        spec=self._lcd_current_spec()
        if not flow or spec is None or spec.get("type")!="choice":
            return False
        codes=list(spec["choices"])
        try:
            current=self._lcd_real(self.expr.get(),spec.get("label",spec["key"]),integer=True)
            index=codes.index(current)
        except Exception:
            index=0
        code=codes[(index+direction)%len(codes)]
        flow.setdefault("draft",{})[spec["key"]]=str(code)
        self._set_lcd_expression(code)
        self._lcd_render_field()
        return True

    def _lcd_submit(self):
        flow=self.__dict__.get("_lcd_flow")
        if not flow:
            return
        if flow.get("phase")=="sheet":
            self._lcd_submit_sheet()
            return
        if flow.get("phase")=="results":
            self._start_lcd_flow(flow["mode"])
            return
        spec=self._lcd_current_spec()
        if spec is None:
            return
        try:
            value=self._lcd_parse_field(spec,self.expr.get())
        except Exception as exc:
            self._lcd_error(exc)
            return
        flow.setdefault("values",{})[spec["key"]]=value
        flow.setdefault("draft",{}).pop(spec["key"],None)
        if flow["index"]<len(flow["fields"])-1:
            flow["index"]+=1
            self._lcd_render_field()
            return
        try:
            self._lcd_complete_flow()
        except Exception as exc:
            self._lcd_error(exc)

    def _lcd_vertical_move(self,direction):
        flow=self.__dict__.get("_lcd_flow")
        if not flow:
            return False
        if flow.get("phase")=="sheet":
            return self._lcd_move_sheet_row(direction)
        if flow.get("phase")=="results":
            lines=flow.get("result_lines",[])
            if lines:
                flow["result_index"]=max(0,min(len(lines)-1,flow.get("result_index",0)+direction))
                self._lcd_render_result()
            return True
        if flow.get("phase")=="form":
            self._lcd_capture_draft()
            flow["index"]=max(0,min(len(flow["fields"])-1,flow["index"]+direction))
            self._lcd_render_field()
            return True
        return False

    def _lcd_move(self,direction):
        flow=self.__dict__.get("_lcd_flow")
        if not flow:
            return False
        if flow.get("phase")=="sheet":
            return self._lcd_move_sheet_column(direction)
        return self._lcd_cycle_choice(direction)

    def _lcd_keypress(self,event):
        flow=self.__dict__.get("_lcd_flow")
        if not flow:
            return None
        if flow.get("phase")=="form":
            if (event.char and event.char.isprintable()) or event.keysym in {"BackSpace","Delete"}:
                flow["field_armed"]=False
            return None
        if flow.get("phase")!="sheet":
            return None
        if (
            flow.get("sheet_phase")=="browse"
            and event.keysym not in {"Left","Right","Up","Down","Return","KP_Enter","Escape"}
            and (event.char and event.char.isprintable() or event.keysym in {"BackSpace","Delete"})
        ):
            flow["editing"]=True
        return None

    def _keyboard_character_token(self, char):
        """Return the calculator-key equivalent of a typed character, if any."""
        if char in self.KEYBOARD_CHARACTER_MAP:
            return self.KEYBOARD_CHARACTER_MAP[char]
        if char.isdigit() or char in self.KEYBOARD_VARIABLES:
            return char
        if char == "i" and getattr(self,"mode","Calculate")=="Complex":
            return char
        return None

    def _physical_keypress(self,event):
        """Route physical keys through the same public operations as LCD keys."""
        if self.__dict__.get("_calculation_busy",False):
            if event.keysym == "Escape":
                self.ac_key()
            return "break"
        if self.template_kind:
            return None
        if event.keysym in {"Return","KP_Enter"}:
            self.equals(); return "break"
        if event.keysym in {"Escape"}:
            self.ac_key(); return "break"
        if event.keysym in {"BackSpace","Delete"}:
            self.del_key(); return "break"
        if event.keysym in {"Left","Right"}:
            self.move(-1 if event.keysym=="Left" else 1); return "break"
        if event.keysym in {"Up","Down"}:
            self.vertical_move(-1 if event.keysym=="Up" else 1); return "break"
        # Block paste and modifier combinations so they cannot bypass the
        # visible-key restriction.  F1/Escape are handled at the root level.
        if event.state & 0x4 or event.state & 0x8:
            return "break"
        if event.char and event.char.isprintable():
            token=self._keyboard_character_token(event.char)
            if token is not None:
                self.insert(token)
            return "break"
        return None

    def _lcd_options(self):
        flow=self.__dict__.get("_lcd_flow")
        if not flow:
            return
        if flow["mode"]=="Spreadsheet":
            if flow.get("phase")=="results":
                self._lcd_start_sheet()
            elif flow.get("editing"):
                self._lcd_error(CalculatorError("Save or cancel the cell edit before opening tools"))
            else:
                self._lcd_sheet_tools()
        else:
            self._start_lcd_flow(flow["mode"])

    def _start_lcd_flow(self,mode):
        self.cancel_template()
        self._lcd_flow={"mode":mode,"values":{},"draft":{},"last_error":""}
        starters={
            "Integral":self._lcd_start_integral,
            "Complex Integral":self._lcd_start_complex_integral,
            "Matrix":self._lcd_start_matrix,
            "Vector":self._lcd_start_vector,
            "Statistics":self._lcd_start_statistics,
            "Distribution":self._lcd_start_distribution,
            "Spreadsheet":self._lcd_start_sheet,
            "Table":self._lcd_start_table,
            "Equation/Func":self._lcd_start_equation,
            "Inequality":self._lcd_start_inequality,
            "Ratio":self._lcd_start_ratio,
            "History":self._lcd_start_history,
        }
        starters[mode]()

    def _lcd_start_history(self):
        # The engine keeps history in calculation order for Ans and ordinary
        # input recall.  The LCD list is a newest-first view: entry 1 is the
        # most recently completed calculation.
        entries=list(reversed(self._history_entries()))
        lines=[self._history_line(expression,result) for expression,result in entries] or ["No saved calculations"]
        self._lcd_show_results("HISTORY",lines)

    @staticmethod
    def _lcd_calculus_variable_field(key,label,default):
        return App._lcd_choice_field(
            key,label,{1:"x",2:"y",3:"z",4:"t",5:"u",6:"v"},default,
        )

    @staticmethod
    def _lcd_calculus_text_field(key,label,default):
        return {"key":key,"label":label,"type":"raw","default":default}

    def _lcd_start_integral(self):
        self._lcd_flow["source_expression"]=self.expr.get().strip()
        actions={
            1:"Definite Integral",2:"Indefinite Integral",3:"Indefinite Derivative",
            4:"Double Integral",5:"Triple Integral",6:"Line Integral (f ds)",
            7:"Line Integral (P dx + Q dy)",8:"Surface Integral (f dS)",9:"Surface Flux Integral",
        }
        self._lcd_begin_form("INTEGRAL",[self._lcd_choice_field("calculus_action","type",actions)],"calculus_action")

    def _lcd_start_complex_integral(self):
        self._lcd_flow["source_expression"]=self.expr.get().strip()
        actions={
            1:"Complex Definite Integral",2:"Complex Indefinite Integral",3:"Complex Double Integral",
            4:"Contour Integral",5:"Indefinite Derivative",
        }
        self._lcd_begin_form("CPLX INT",[self._lcd_choice_field("calculus_action","type",actions)],"calculus_action")

    def _lcd_choose_calculus_action(self):
        flow=self._lcd_flow; action=flow["values"]["calculus_action"]
        source=flow.get("source_expression","")
        if action in {"Definite Integral","Complex Definite Integral"}:
            self._reset_lcd_flow()
            self.set_expr(source)
            self.start_integral_template()
            return
        expression_default=source or "x^2"
        if action in {"Indefinite Integral","Complex Indefinite Integral","Indefinite Derivative"}:
            fields=[
                self._lcd_calculus_text_field("calculus_expression","f(variable)",expression_default),
                self._lcd_calculus_variable_field("calculus_variable","d variable","z" if action.startswith("Complex") else "x"),
            ]
        elif action=="Double Integral":
            fields=[
                self._lcd_calculus_text_field("calculus_expression","f(x,y)",source or "x+y"),
                self._lcd_calculus_variable_field("outer_variable","outer d","x"),
                self._lcd_calculus_variable_field("inner_variable","inner d","y"),
                self._lcd_calculus_text_field("outer_lower","outer lower","0"),
                self._lcd_calculus_text_field("outer_upper","outer upper","1"),
                self._lcd_calculus_text_field("inner_lower","inner lower","0"),
                self._lcd_calculus_text_field("inner_upper","inner upper","1"),
            ]
        elif action=="Triple Integral":
            fields=[
                self._lcd_calculus_text_field("calculus_expression","f(x,y,z)",source or "x+y+z"),
                self._lcd_calculus_variable_field("outer_variable","outer d","x"),
                self._lcd_calculus_variable_field("middle_variable","middle d","y"),
                self._lcd_calculus_variable_field("inner_variable","inner d","z"),
                self._lcd_calculus_text_field("outer_lower","outer lower","0"),
                self._lcd_calculus_text_field("outer_upper","outer upper","1"),
                self._lcd_calculus_text_field("middle_lower","middle lower","0"),
                self._lcd_calculus_text_field("middle_upper","middle upper","1"),
                self._lcd_calculus_text_field("inner_lower","inner lower","0"),
                self._lcd_calculus_text_field("inner_upper","inner upper","1"),
            ]
        elif action=="Complex Double Integral":
            fields=[
                self._lcd_calculus_text_field("calculus_expression","f(x,y)",source or "i*x+y"),
                self._lcd_calculus_variable_field("outer_variable","outer d","x"),
                self._lcd_calculus_variable_field("inner_variable","inner d","y"),
                self._lcd_calculus_text_field("outer_lower","outer lower","0"),
                self._lcd_calculus_text_field("outer_upper","outer upper","1"),
                self._lcd_calculus_text_field("inner_lower","inner lower","0"),
                self._lcd_calculus_text_field("inner_upper","inner upper","1"),
            ]
        elif action=="Line Integral (f ds)":
            fields=[
                self._lcd_calculus_text_field("calculus_expression","f(x,y)",source or "1"),
                self._lcd_calculus_text_field("path_x","x(parameter)","t"),
                self._lcd_calculus_text_field("path_y","y(parameter)","t^2"),
                self._lcd_calculus_variable_field("parameter","parameter","t"),
                self._lcd_calculus_text_field("path_lower","parameter lower","0"),
                self._lcd_calculus_text_field("path_upper","parameter upper","1"),
            ]
        elif action=="Line Integral (P dx + Q dy)":
            fields=[
                self._lcd_calculus_text_field("component_x","P(x,y)",source or "y"),
                self._lcd_calculus_text_field("component_y","Q(x,y)","x"),
                self._lcd_calculus_text_field("path_x","x(parameter)","t"),
                self._lcd_calculus_text_field("path_y","y(parameter)","t^2"),
                self._lcd_calculus_variable_field("parameter","parameter","t"),
                self._lcd_calculus_text_field("path_lower","parameter lower","0"),
                self._lcd_calculus_text_field("path_upper","parameter upper","1"),
            ]
        elif action in {"Surface Integral (f dS)","Surface Flux Integral"}:
            fields=[]
            if action=="Surface Flux Integral":
                fields.extend([
                    self._lcd_calculus_text_field("component_x","P(x,y,z)",source or "0"),
                    self._lcd_calculus_text_field("component_y","Q(x,y,z)","0"),
                    self._lcd_calculus_text_field("component_z","R(x,y,z)","1"),
                ])
            else:
                fields.append(self._lcd_calculus_text_field("calculus_expression","f(x,y,z)",source or "1"))
            fields.extend([
                self._lcd_calculus_text_field("surface_x","x(u,v)","u"),
                self._lcd_calculus_text_field("surface_y","y(u,v)","v"),
                self._lcd_calculus_text_field("surface_z","z(u,v)","0"),
                self._lcd_calculus_variable_field("outer_variable","outer parameter","u"),
                self._lcd_calculus_variable_field("inner_variable","inner parameter","v"),
                self._lcd_calculus_text_field("outer_lower","outer lower","0"),
                self._lcd_calculus_text_field("outer_upper","outer upper","1"),
                self._lcd_calculus_text_field("inner_lower","inner lower","0"),
                self._lcd_calculus_text_field("inner_upper","inner upper","1"),
            ])
            if action=="Surface Flux Integral":
                fields.append(self._lcd_choice_field("flux_orientation","normal",{1:"r_outer × r_inner",2:"reverse"}))
        elif action=="Contour Integral":
            fields=[
                self._lcd_calculus_text_field("calculus_expression","f(z)",source or "1/z"),
                self._lcd_calculus_text_field("contour_path","z(parameter)","exp(i*t)"),
                self._lcd_calculus_variable_field("complex_variable","d variable","z"),
                self._lcd_calculus_variable_field("parameter","parameter","t"),
                self._lcd_calculus_text_field("path_lower","parameter lower","0"),
                self._lcd_calculus_text_field("path_upper","parameter upper","2*pi"),
            ]
        else:
            raise CalculatorError("Argument ERROR: unsupported calculus operation")
        self._lcd_begin_form("CPLX INT" if flow["mode"]=="Complex Integral" else "INTEGRAL",fields,"calculus_run")

    def _lcd_run_calculus_operation(self):
        flow=self._lcd_flow; values=flow["values"]; action=values["calculus_action"]
        if action in {"Indefinite Integral","Complex Indefinite Integral"}:
            method,args,title="symbolic_integral",(values["calculus_expression"],values["calculus_variable"]),"INTEGRAL"
            prefix=f"∫ d{values['calculus_variable']}"
            approximate=False
        elif action=="Indefinite Derivative":
            method,args,title="symbolic_derivative",(values["calculus_expression"],values["calculus_variable"]),"DERIVATIVE"
            prefix=f"d/d{values['calculus_variable']}"
            approximate=False
        elif action in {"Double Integral","Complex Double Integral"}:
            method="complex_double_integral" if action.startswith("Complex") else "double_integral"
            args=(
                values["calculus_expression"],values["outer_lower"],values["outer_upper"],
                values["inner_lower"],values["inner_upper"],values["outer_variable"],values["inner_variable"],
            )
            title="CPLX INT" if action.startswith("Complex") else "INTEGRAL"; prefix="∫∫"; approximate=True
        elif action=="Triple Integral":
            method="triple_integral"
            args=(
                values["calculus_expression"],values["outer_lower"],values["outer_upper"],
                values["middle_lower"],values["middle_upper"],values["inner_lower"],values["inner_upper"],
                values["outer_variable"],values["middle_variable"],values["inner_variable"],
            )
            title="INTEGRAL"; prefix="∫∫∫"; approximate=True
        elif action=="Line Integral (f ds)":
            method="line_integral"
            args=(values["calculus_expression"],values["path_x"],values["path_y"],values["path_lower"],values["path_upper"],values["parameter"])
            title="LINE"; prefix="∫C"; approximate=True
        elif action=="Line Integral (P dx + Q dy)":
            method="vector_line_integral"
            args=(values["component_x"],values["component_y"],values["path_x"],values["path_y"],values["path_lower"],values["path_upper"],values["parameter"])
            title="LINE"; prefix="∫C"; approximate=True
        elif action=="Surface Integral (f dS)":
            method="surface_integral"
            args=(
                values["calculus_expression"],values["surface_x"],values["surface_y"],values["surface_z"],
                values["outer_lower"],values["outer_upper"],values["inner_lower"],values["inner_upper"],
                values["outer_variable"],values["inner_variable"],
            )
            title="SURFACE"; prefix="∫∫S"; approximate=True
        elif action=="Surface Flux Integral":
            method="surface_flux_integral"
            args=(
                values["component_x"],values["component_y"],values["component_z"],
                values["surface_x"],values["surface_y"],values["surface_z"],
                values["outer_lower"],values["outer_upper"],values["inner_lower"],values["inner_upper"],
                values["outer_variable"],values["inner_variable"],values["flux_orientation"]=="reverse",
            )
            title="FLUX"; prefix="Φ"; approximate=True
        elif action=="Contour Integral":
            method="contour_integral"
            args=(
                values["calculus_expression"],values["contour_path"],values["path_lower"],values["path_upper"],
                values["complex_variable"],values["parameter"],
            )
            title="CPLX INT"; prefix="∫γ"; approximate=True
        else:
            raise CalculatorError("Argument ERROR: unsupported calculus operation")

        def success(result):
            text=self.core.format_result(result,approximate=approximate)
            if action in {"Indefinite Integral","Complex Indefinite Integral"}:
                text+=" + C"
            self._lcd_show_results(title,[f"{prefix} = {text}"])
            self.history_pos=max(0,len(self.core.history)-1)

        self._run_background_calculation(method,args,success)

    @staticmethod
    def _lcd_choice_field(key,label,choices,default=None):
        if default is None:
            default=next(iter(choices.values()))
        return {"key":key,"label":label,"type":"choice","choices":choices,"default":default}

    @staticmethod
    def _lcd_number_field(key,label,default="",integer=False,minimum=None,maximum=None):
        field={"key":key,"label":label,"type":"integer" if integer else "number","default":default}
        if minimum is not None: field["minimum"]=minimum
        if maximum is not None: field["maximum"]=maximum
        return field

    @staticmethod
    def _lcd_matrix_choices(include_ans=False):
        choices={1:"MatA",2:"MatB",3:"MatC",4:"MatD"}
        if include_ans:
            choices[5]="MatAns"
        return choices

    @staticmethod
    def _lcd_vector_choices(include_ans=False):
        choices={1:"VctA",2:"VctB",3:"VctC",4:"VctD"}
        if include_ans:
            choices[5]="VctAns"
        return choices

    def _lcd_array_lines(self,title,value):
        data=np.asarray(value)
        if data.ndim==0:
            return [f"{title} = {self._lcd_number_text(data.item())}"]
        if data.ndim==1:
            return [f"{title} = ["+", ".join(self._lcd_number_text(item) for item in data)+"]"]
        return [
            f"{title} r{row+1}: ["+", ".join(self._lcd_number_text(item) for item in data[row])+"]"
            for row in range(data.shape[0])
        ]

    def _lcd_complete_flow(self):
        flow=self._lcd_flow
        handlers={
            "calculus_action":self._lcd_choose_calculus_action,
            "calculus_run":self._lcd_run_calculus_operation,
            "matrix_action":self._lcd_choose_matrix_action,
            "matrix_shape":self._lcd_expand_matrix_values,
            "matrix_values":self._lcd_define_matrix,
            "matrix_operation":self._lcd_run_matrix_operation,
            "matrix_identity":self._lcd_run_matrix_identity,
            "matrix_copy":self._lcd_run_matrix_copy,
            "vector_action":self._lcd_choose_vector_action,
            "vector_shape":self._lcd_expand_vector_values,
            "vector_values":self._lcd_define_vector,
            "vector_operation":self._lcd_run_vector_operation,
            "vector_copy":self._lcd_run_vector_copy,
            "statistics_action":self._lcd_choose_statistics_action,
            "statistics_run":self._lcd_run_statistics,
            "distribution_kind":self._lcd_choose_distribution_kind,
            "distribution_run":self._lcd_run_distribution,
            "table_run":self._lcd_run_table,
            "equation_kind":self._lcd_choose_equation_kind,
            "equation_ode":self._lcd_expand_ode_conditions,
            "equation_ode_run":self._lcd_run_differential_equation,
            "equation_poly_degree":self._lcd_expand_polynomial_values,
            "equation_poly_values":self._lcd_run_polynomial,
            "equation_simul_size":self._lcd_expand_simultaneous_values,
            "equation_simul_values":self._lcd_run_simultaneous,
            "inequality_degree":self._lcd_expand_inequality_values,
            "inequality_values":self._lcd_run_inequality,
            "ratio_kind":self._lcd_choose_ratio_kind,
            "ratio_values":self._lcd_run_ratio,
            "sheet_tool":self._lcd_choose_sheet_tool,
            "sheet_copy":self._lcd_run_sheet_copy,
            "sheet_cut":self._lcd_run_sheet_cut,
            "sheet_grab":self._lcd_run_sheet_grab,
            "sheet_fill_value":self._lcd_run_sheet_fill_value,
            "sheet_fill_formula":self._lcd_run_sheet_fill_formula,
            "sheet_delete_all":self._lcd_run_sheet_delete_all,
        }
        handler=handlers.get(flow.get("stage"))
        if handler is None:
            raise CalculatorError("Argument ERROR: unsupported LCD workflow")
        handler()

    # Matrix -----------------------------------------------------------------
    def _lcd_start_matrix(self):
        actions={
            1:"Define / Edit",2:"A + B",3:"A - B",4:"A × B",5:"det(A)",
            6:"A⁻¹",7:"Trn(A)",8:"A²",9:"A³",10:"Abs(A)",11:"Identity",12:"Copy",
        }
        self._lcd_begin_form("MATRIX",[self._lcd_choice_field("action","action",actions)],"matrix_action")

    def _lcd_choose_matrix_action(self):
        flow=self._lcd_flow; action=flow["values"]["action"]
        if action=="Define / Edit":
            self._lcd_begin_form("MATRIX define",[
                self._lcd_choice_field("matrix_name","name",self._lcd_matrix_choices()),
                self._lcd_number_field("matrix_rows","rows",2,integer=True,minimum=1,maximum=4),
                self._lcd_number_field("matrix_cols","columns",2,integer=True,minimum=1,maximum=4),
            ],"matrix_shape")
            return
        if action=="Identity":
            self._lcd_begin_form("MATRIX identity",[self._lcd_number_field("matrix_size","size",2,integer=True,minimum=1,maximum=4)],"matrix_identity")
            return
        if action=="Copy":
            self._lcd_begin_form("MATRIX copy",[
                self._lcd_choice_field("matrix_source","source",self._lcd_matrix_choices(True)),
                self._lcd_choice_field("matrix_destination","destination",self._lcd_matrix_choices()),
            ],"matrix_copy")
            return
        operation={"A + B":"+","A - B":"-","A × B":"*","det(A)":"det","A⁻¹":"inv","Trn(A)":"trn","A²":"square","A³":"cube","Abs(A)":"abs"}[action]
        fields=[self._lcd_choice_field("matrix_a","first matrix",self._lcd_matrix_choices(True))]
        if operation in {"+","-","*"}:
            fields.append(self._lcd_choice_field("matrix_b","second matrix",self._lcd_matrix_choices(True)))
        flow["matrix_operation"]=operation
        self._lcd_begin_form("MATRIX "+action,fields,"matrix_operation")

    def _lcd_expand_matrix_values(self):
        flow=self._lcd_flow; rows=flow["values"]["matrix_rows"]; cols=flow["values"]["matrix_cols"]
        name=flow["values"]["matrix_name"]
        fields=[self._lcd_number_field(f"matrix_{row}_{col}",f"r{row+1} c{col+1}",0) for row in range(rows) for col in range(cols)]
        self._lcd_begin_form(f"{name} {rows}×{cols}",fields,"matrix_values")

    def _lcd_define_matrix(self):
        flow=self._lcd_flow; rows=flow["values"]["matrix_rows"]; cols=flow["values"]["matrix_cols"]
        data=np.array([[flow["values"][f"matrix_{row}_{col}"] for col in range(cols)] for row in range(rows)])
        name=flow["values"]["matrix_name"]
        self.core.define_matrix(name,data)
        self._lcd_show_results("MATRIX",self._lcd_array_lines(name,data))

    def _lcd_run_matrix_operation(self):
        flow=self._lcd_flow; operation=flow["matrix_operation"]
        result=self.core.matrix_op(operation,flow["values"]["matrix_a"],flow["values"].get("matrix_b"))
        self._lcd_show_results("MATRIX",self._lcd_array_lines(operation,result))

    def _lcd_run_matrix_identity(self):
        result=self.core.identity(self._lcd_flow["values"]["matrix_size"])
        self._lcd_show_results("MATRIX",self._lcd_array_lines("I",result))

    def _lcd_run_matrix_copy(self):
        values=self._lcd_flow["values"]; source=values["matrix_source"]; destination=values["matrix_destination"]
        data=self.core.mat_ans if source=="MatAns" else self.core.matrices.get(source)
        if data is None:
            raise CalculatorError("Dimension ERROR")
        self.core.matrices[destination]=np.array(data,copy=True)
        self._lcd_show_results("MATRIX",[f"{source} → {destination}"])

    # Vector -----------------------------------------------------------------
    def _lcd_start_vector(self):
        actions={1:"Define / Edit",2:"A + B",3:"A - B",4:"Dot",5:"Cross",6:"Angle",7:"Abs",8:"Unit",9:"Scalar ×",10:"Copy"}
        self._lcd_begin_form("VECTOR",[self._lcd_choice_field("action","action",actions)],"vector_action")

    def _lcd_choose_vector_action(self):
        flow=self._lcd_flow; action=flow["values"]["action"]
        if action=="Define / Edit":
            self._lcd_begin_form("VECTOR define",[
                self._lcd_choice_field("vector_name","name",self._lcd_vector_choices()),
                self._lcd_number_field("vector_dimension","dimension",2,integer=True,minimum=2,maximum=3),
            ],"vector_shape")
            return
        if action=="Copy":
            self._lcd_begin_form("VECTOR copy",[
                self._lcd_choice_field("vector_source","source",self._lcd_vector_choices(True)),
                self._lcd_choice_field("vector_destination","destination",self._lcd_vector_choices()),
            ],"vector_copy")
            return
        operation={"A + B":"+","A - B":"-","Dot":"dot","Cross":"cross","Angle":"angle","Abs":"abs","Unit":"unit","Scalar ×":"scale"}[action]
        fields=[self._lcd_choice_field("vector_a","first vector",self._lcd_vector_choices(True))]
        if operation in {"+","-","dot","cross","angle"}:
            fields.append(self._lcd_choice_field("vector_b","second vector",self._lcd_vector_choices(True)))
        if operation=="scale":
            fields.append(self._lcd_number_field("vector_scalar","scalar",1))
        flow["vector_operation"]=operation
        self._lcd_begin_form("VECTOR "+action,fields,"vector_operation")

    def _lcd_expand_vector_values(self):
        flow=self._lcd_flow; dimension=flow["values"]["vector_dimension"]; name=flow["values"]["vector_name"]
        fields=[self._lcd_number_field(f"vector_{index}",f"component {index+1}",0) for index in range(dimension)]
        self._lcd_begin_form(f"{name} {dimension}D",fields,"vector_values")

    def _lcd_define_vector(self):
        flow=self._lcd_flow; dimension=flow["values"]["vector_dimension"]
        data=np.array([flow["values"][f"vector_{index}"] for index in range(dimension)])
        name=flow["values"]["vector_name"]
        self.core.define_vector(name,data)
        self._lcd_show_results("VECTOR",self._lcd_array_lines(name,data))

    def _lcd_run_vector_operation(self):
        flow=self._lcd_flow; values=flow["values"]
        result=self.core.vector_op(flow["vector_operation"],values["vector_a"],values.get("vector_b"),values.get("vector_scalar"))
        self._lcd_show_results("VECTOR",self._lcd_array_lines(flow["vector_operation"],result))

    def _lcd_run_vector_copy(self):
        values=self._lcd_flow["values"]; source=values["vector_source"]; destination=values["vector_destination"]
        data=self.core.vct_ans if source=="VctAns" else self.core.vectors.get(source)
        if data is None:
            raise CalculatorError("Dimension ERROR")
        self.core.vectors[destination]=np.array(data,copy=True)
        self._lcd_show_results("VECTOR",[f"{source} → {destination}"])

    # Statistics -------------------------------------------------------------
    def _lcd_start_statistics(self):
        analyses={1:"1-Variable",2:"Linear",3:"Quadratic",4:"Logarithmic",5:"e Exponential",6:"ab Exponential",7:"Power",8:"Inverse",9:"P(t)",10:"Q(t)",11:"R(t)",12:"x→t"}
        self._lcd_begin_form("STAT",[self._lcd_choice_field("analysis","analysis",analyses)],"statistics_action")

    def _lcd_choose_statistics_action(self):
        flow=self._lcd_flow; analysis=flow["values"]["analysis"]
        if analysis=="1-Variable":
            fields=[{"key":"stat_x","label":"x values (comma)","type":"numbers","default":""}]
            if self.core.settings.statistics_freq:
                fields.append({"key":"stat_frequency","label":"frequencies (comma)","type":"numbers","default":""})
        elif analysis in {"P(t)","Q(t)","R(t)"}:
            fields=[self._lcd_number_field("stat_t","t",0)]
        elif analysis=="x→t":
            fields=[{"key":"stat_x","label":"x values (comma)","type":"numbers","default":""}]
            if self.core.settings.statistics_freq:
                fields.append({"key":"stat_frequency","label":"frequencies (comma)","type":"numbers","default":""})
            fields.append(self._lcd_number_field("stat_target","x",0))
        else:
            fields=[
                {"key":"stat_x","label":"x values (comma)","type":"numbers","default":""},
                {"key":"stat_y","label":"y values (comma)","type":"numbers","default":""},
            ]
        self._lcd_begin_form("STAT "+analysis,fields,"statistics_run")

    def _lcd_run_statistics(self):
        values=self._lcd_flow["values"]; analysis=values["analysis"]
        if analysis=="1-Variable":
            result=self.core.one_var_stats(values["stat_x"],values.get("stat_frequency"))
            lines=[f"{key} = {self._lcd_number_text(value) if math.isfinite(float(value)) else 'n/a'}" for key,value in result.items()]
        elif analysis in {"P(t)","Q(t)","R(t)"}:
            fn={"P(t)":self.core.normal_P,"Q(t)":self.core.normal_Q,"R(t)":self.core.normal_R}[analysis]
            lines=[f"{analysis} = {fn(values['stat_t']):.12g}"]
        elif analysis=="x→t":
            stats=self.core.one_var_stats(values["stat_x"],values.get("stat_frequency"))
            if stats["σx"]==0:
                raise CalculatorError("Math ERROR: standard deviation is zero")
            lines=[f"t = {(values['stat_target']-stats['x̄'])/stats['σx']:.12g}"]
        else:
            kind={"Linear":"linear","Quadratic":"quadratic","Logarithmic":"log","e Exponential":"exp_e","ab Exponential":"exp_b","Power":"power","Inverse":"inverse"}[analysis]
            result=self.core.regression(values["stat_x"],values["stat_y"],kind)
            lines=[f"{key} = {self._lcd_number_text(value) if math.isfinite(float(value)) else 'n/a'}" for key,value in result.items() if key!="predict"]
        self._lcd_show_results("STAT",lines)

    # Distribution -----------------------------------------------------------
    def _lcd_start_distribution(self):
        kinds={1:"Normal PD",2:"Normal CD",3:"Inverse Normal",4:"Binomial PD",5:"Binomial CD",6:"Poisson PD",7:"Poisson CD"}
        self._lcd_begin_form("DIST",[self._lcd_choice_field("distribution_kind","type",kinds)],"distribution_kind")

    def _lcd_choose_distribution_kind(self):
        kind=self._lcd_flow["values"]["distribution_kind"]
        definitions={
            "Normal PD":[("x","x",0),("sigma","σ",1),("mu","μ",0)],
            "Normal CD":[("lower","lower",-1),("upper","upper",1),("sigma","σ",1),("mu","μ",0)],
            "Inverse Normal":[("area","area",0.5),("sigma","σ",1),("mu","μ",0)],
            "Binomial PD":[("x","x",0),("N","N",1),("p","p",0.5)],
            "Binomial CD":[("x","x",0),("N","N",1),("p","p",0.5)],
            "Poisson PD":[("x","x",0),("lam","lambda",1)],
            "Poisson CD":[("x","x",0),("lam","lambda",1)],
        }
        fields=[]
        for key,label,default in definitions[kind]:
            integer=key in {"x","N"} and kind.startswith(("Binomial","Poisson"))
            fields.append(self._lcd_number_field(key,label,default,integer=integer,minimum=0 if integer else None))
        self._lcd_begin_form("DIST "+kind,fields,"distribution_run")

    def _lcd_run_distribution(self):
        values=self._lcd_flow["values"]; kind=values["distribution_kind"]
        fields={
            "Normal PD":["x","sigma","mu"],"Normal CD":["lower","upper","sigma","mu"],"Inverse Normal":["area","sigma","mu"],
            "Binomial PD":["x","N","p"],"Binomial CD":["x","N","p"],"Poisson PD":["x","lam"],"Poisson CD":["x","lam"],
        }[kind]
        result=self.core.distribution(kind,**{key:values[key] for key in fields})
        self._lcd_show_results("DIST",[f"{kind} = {result:.12g}"])

    # Table ------------------------------------------------------------------
    def _lcd_start_table(self):
        fields=[{"key":"table_f","label":"f(x)","type":"function","default":"x^2"}]
        if self.core.settings.table_two_functions:
            fields.append({"key":"table_g","label":"g(x)","type":"function","default":"x^2+1"})
        fields.extend([
            self._lcd_number_field("table_start","start",-1),
            self._lcd_number_field("table_end","end",1),
            self._lcd_number_field("table_step","step",0.5),
        ])
        self._lcd_begin_form("TABLE",fields,"table_run")

    def _lcd_run_table(self):
        values=self._lcd_flow["values"]; has_g="table_g" in values
        count=self._table_row_count(values["table_start"],values["table_end"],values["table_step"],has_g)
        rows=[]
        for index in range(count):
            x_value=values["table_start"]+index*values["table_step"]
            x_symbol=sp.Float(x_value)
            f_value=self._lcd_real_expression(self.core.parse(values["table_f"],{"x":x_symbol}),"table result")
            row=f"x={x_value:.12g}  f={f_value:.12g}"
            if has_g:
                g_value=self._lcd_real_expression(self.core.parse(values["table_g"],{"x":x_symbol}),"table result")
                row+=f"  g={g_value:.12g}"
            rows.append(row)
        self.core.memory["x"]=sp.Float(values["table_start"]+(count-1)*values["table_step"])
        self._lcd_show_results("TABLE",rows)

    # Equation / inequality / ratio -----------------------------------------
    def _lcd_start_equation(self):
        kinds={1:"Polynomial",2:"Simultaneous",3:"Differential Equation"}
        self._lcd_begin_form("EQUATION",[self._lcd_choice_field("equation_kind","type",kinds)],"equation_kind")

    def _lcd_choose_equation_kind(self):
        kind=self._lcd_flow["values"]["equation_kind"]
        if kind=="Polynomial":
            self._lcd_begin_form("POLYNOMIAL",[self._lcd_number_field("polynomial_degree","degree",2,integer=True,minimum=2,maximum=4)],"equation_poly_degree")
        elif kind=="Simultaneous":
            self._lcd_begin_form("SIMULTANEOUS",[self._lcd_number_field("simultaneous_size","unknowns",2,integer=True,minimum=2,maximum=4)],"equation_simul_size")
        else:
            self._lcd_begin_form("DIFF EQ",[
                self._lcd_calculus_text_field("ode_equation","dy/dx =", "dy/dx=y"),
                self._lcd_calculus_variable_field("ode_dependent_variable","dependent", "y"),
                self._lcd_calculus_variable_field("ode_independent_variable","independent", "x"),
                self._lcd_choice_field("ode_condition_mode","conditions",{1:"General",2:"y(x0)",3:"y(x0), y'(x0)"}),
            ],"equation_ode")

    def _lcd_expand_ode_conditions(self):
        values=self._lcd_flow["values"]
        if values["ode_dependent_variable"]==values["ode_independent_variable"]:
            raise CalculatorError("Syntax ERROR: dependent and independent variables must differ")
        mode=values["ode_condition_mode"]
        if mode=="General":
            self._lcd_run_differential_equation()
            return
        fields=[
            self._lcd_calculus_text_field("ode_initial_point","x0","0"),
            self._lcd_calculus_text_field("ode_initial_value","y(x0)","1"),
        ]
        if mode=="y(x0), y'(x0)":
            fields.append(self._lcd_calculus_text_field("ode_initial_derivative","y'(x0)","0"))
        self._lcd_begin_form("DIFF EQ",fields,"equation_ode_run")

    def _lcd_run_differential_equation(self):
        values=self._lcd_flow["values"]
        conditions=None
        if values["ode_condition_mode"]!="General":
            conditions={
                "x0":values["ode_initial_point"],
                "y0":values["ode_initial_value"],
            }
            if values["ode_condition_mode"]=="y(x0), y'(x0)":
                conditions["dy0"]=values["ode_initial_derivative"]

        def success(result):
            if isinstance(result,sp.Equality):
                text=f"{result.lhs} = {self.core.format_result(result.rhs)}"
            else:
                text=self.core.format_result(result)
            self._lcd_show_results("DIFF EQ",[text])
            self.history_pos=max(0,len(self.core.history)-1)

        self._run_background_calculation(
            "solve_ode",(
                values["ode_equation"],values["ode_dependent_variable"],values["ode_independent_variable"],conditions,
            ),success,
        )

    def _lcd_expand_polynomial_values(self):
        degree=self._lcd_flow["values"]["polynomial_degree"]
        fields=[self._lcd_number_field(f"polynomial_{index}",f"coefficient a{degree-index}",0) for index in range(degree+1)]
        self._lcd_begin_form(f"POLY {degree}",fields,"equation_poly_values")

    @staticmethod
    def _lcd_complex_text(value):
        number=complex(value)
        if abs(number.imag)<1e-10:
            return f"{number.real:.12g}"
        return f"{number.real:.12g}{number.imag:+.12g}i"

    def _lcd_run_polynomial(self):
        values=self._lcd_flow["values"]; degree=values["polynomial_degree"]
        coefficients=[values[f"polynomial_{index}"] for index in range(degree+1)]
        roots=self.core.polynomial_roots(coefficients)
        lines=[f"x{index+1} = {self._lcd_complex_text(root)}" for index,root in enumerate(roots)]
        if degree==2:
            a,b,c=coefficients; x_value=-b/(2*a); y_value=a*x_value*x_value+b*x_value+c
            lines.append(f"Vertex = ({x_value:.12g}, {y_value:.12g})")
        self._lcd_show_results("EQUATION",lines)

    def _lcd_expand_simultaneous_values(self):
        size=self._lcd_flow["values"]["simultaneous_size"]
        fields=[self._lcd_number_field(f"simul_{row}_{col}",f"a{row+1}{col+1}",0) for row in range(size) for col in range(size)]
        fields.extend(self._lcd_number_field(f"simul_b_{row}",f"b{row+1}",0) for row in range(size))
        self._lcd_begin_form(f"SIMUL {size}×{size}",fields,"equation_simul_values")

    def _lcd_run_simultaneous(self):
        values=self._lcd_flow["values"]; size=values["simultaneous_size"]
        matrix=np.array([[values[f"simul_{row}_{col}"] for col in range(size)] for row in range(size)])
        constants=np.array([values[f"simul_b_{row}"] for row in range(size)])
        result=self.core.simultaneous(matrix,constants)
        self._lcd_show_results("EQUATION",[f"x{index+1} = {value:.12g}" for index,value in enumerate(result)])

    def _lcd_start_inequality(self):
        self._lcd_begin_form("INEQUALITY",[self._lcd_number_field("inequality_degree","degree",2,integer=True,minimum=2,maximum=4)],"inequality_degree")

    def _lcd_expand_inequality_values(self):
        degree=self._lcd_flow["values"]["inequality_degree"]
        fields=[self._lcd_number_field(f"inequality_{index}",f"coefficient a{degree-index}",0) for index in range(degree+1)]
        fields.append(self._lcd_choice_field("inequality_relation","relation",{1:">",2:"<",3:"≥",4:"≤"}))
        self._lcd_begin_form(f"INEQUALITY {degree}",fields,"inequality_values")

    def _lcd_run_inequality(self):
        values=self._lcd_flow["values"]; degree=values["inequality_degree"]
        coefficients=[values[f"inequality_{index}"] for index in range(degree+1)]
        result=self.core.inequality(coefficients,values["inequality_relation"])
        self._lcd_show_results("INEQUALITY",[str(result)])

    def _lcd_start_ratio(self):
        kinds={1:"A:B = X:D",2:"A:B = C:X"}
        self._lcd_begin_form("RATIO",[self._lcd_choice_field("ratio_kind","form",kinds)],"ratio_kind")

    def _lcd_choose_ratio_kind(self):
        kind=self._lcd_flow["values"]["ratio_kind"]
        fields=[self._lcd_number_field("ratio_A","A",0),self._lcd_number_field("ratio_B","B",1)]
        fields.append(self._lcd_number_field("ratio_D" if kind=="A:B = X:D" else "ratio_C","D" if kind=="A:B = X:D" else "C",1))
        self._lcd_begin_form("RATIO "+kind,fields,"ratio_values")

    def _lcd_run_ratio(self):
        values=self._lcd_flow["values"]; kind=values["ratio_kind"]
        if kind=="A:B = X:D":
            result=self.core.ratio("A:B=X:D",A=values["ratio_A"],B=values["ratio_B"],D=values["ratio_D"])
        else:
            result=self.core.ratio("A:B=C:X",A=values["ratio_A"],B=values["ratio_B"],C=values["ratio_C"])
        if not math.isfinite(float(result)):
            raise CalculatorError("Math ERROR: ratio result must be finite")
        self._lcd_show_results("RATIO",[f"X = {result:.12g}"])

    # Spreadsheet ------------------------------------------------------------
    def _lcd_start_sheet(self):
        self._lcd_flow.update({
            "phase":"sheet", "stage":"sheet", "sheet_phase":"browse",
            "sheet_column":0, "sheet_row":0, "editing":False,
        })
        self._lcd_render_sheet()

    def _lcd_sheet_address(self):
        flow=self._lcd_flow
        return f"{chr(65+flow.get('sheet_column',0))}{flow.get('sheet_row',0)+1}"

    def _lcd_render_sheet(self):
        flow=self.__dict__.get("_lcd_flow")
        if not flow or flow.get("phase")!="sheet":
            return
        address=self._lcd_sheet_address()
        raw=self.sheet.cells.get(address,"")
        if not flow.get("editing"):
            self._set_lcd_expression(raw)
        if flow.get("editing"):
            prompt=f"Edit {address}  = save  AC"
        else:
            shown=self._spreadsheet_display_value(address)
            prompt=f"{address}={shown if shown!='' else 0}  ▲▼ ◀▶  OPTN"
        self.result.config(text=self._lcd_clip(prompt))
        self.expr.focus_set()

    def _lcd_move_sheet_column(self,direction):
        flow=self.__dict__.get("_lcd_flow")
        if not flow or flow.get("phase")!="sheet":
            return False
        if flow.get("editing"):
            return False
        flow["sheet_column"]=max(0,min(4,flow.get("sheet_column",0)+direction))
        self._lcd_render_sheet()
        return True

    def _lcd_move_sheet_row(self,direction):
        flow=self.__dict__.get("_lcd_flow")
        if not flow or flow.get("phase")!="sheet":
            return False
        if flow.get("editing"):
            return True
        flow["sheet_row"]=max(0,min(44,flow.get("sheet_row",0)+direction))
        self._lcd_render_sheet()
        return True

    def _lcd_submit_sheet(self):
        flow=self._lcd_flow
        address=self._lcd_sheet_address()
        raw=self.sheet.cells.get(address,"")
        if flow.get("editing") or self.expr.get()!=raw:
            self.sheet.set(address,self.expr.get())
            flow["editing"]=False
            self._lcd_render_sheet()
            self.result.config(text=self._lcd_clip(f"Saved {address} = {self._spreadsheet_display_value(address) or 0}"))
            return
        flow["editing"]=True
        self.result.config(text=self._lcd_clip(f"Edit {address}  = save  AC"))

    def _lcd_sheet_return(self,message=None):
        flow=self._lcd_flow
        flow.update({"phase":"sheet","stage":"sheet","sheet_phase":"browse","editing":False,"draft":{}})
        self._lcd_render_sheet()
        if message:
            self.result.config(text=self._lcd_clip(message))

    def _lcd_sheet_tools(self):
        tools={
            1:"Edit cell",2:"Delete cell",3:"Copy cell",4:"Cut cell",5:"Fill value",
            6:"Fill formula",7:"Insert reference",8:"Recalculate",9:"Free space",10:"Delete all",
        }
        self._lcd_begin_form("SHEET tools",[self._lcd_choice_field("sheet_tool","tool",tools)],"sheet_tool")

    def _lcd_choose_sheet_tool(self):
        flow=self._lcd_flow; tool=flow["values"]["sheet_tool"]
        if tool=="Edit cell":
            flow.update({"phase":"sheet","stage":"sheet","sheet_phase":"browse","editing":True})
            self._set_lcd_expression(self.sheet.cells.get(self._lcd_sheet_address(),""))
            self.result.config(text=self._lcd_clip(f"Edit {self._lcd_sheet_address()}  = save  AC"))
            return
        if tool=="Delete cell":
            address=self._lcd_sheet_address(); self.sheet.delete(address); self._lcd_sheet_return(f"Deleted {address}")
            return
        if tool in {"Copy cell","Cut cell"}:
            fields=[
                self._lcd_choice_field("sheet_target_column","destination column",{1:"A",2:"B",3:"C",4:"D",5:"E"}),
                self._lcd_number_field("sheet_target_row","destination row",1,integer=True,minimum=1,maximum=45),
            ]
            self._lcd_begin_form("SHEET "+tool,fields,"sheet_copy" if tool=="Copy cell" else "sheet_cut")
            return
        if tool=="Insert reference":
            source=self._lcd_sheet_address()
            fields=[
                self._lcd_choice_field("sheet_target_column","destination column",{1:"A",2:"B",3:"C",4:"D",5:"E"}),
                self._lcd_number_field("sheet_target_row","destination row",1,integer=True,minimum=1,maximum=45),
                {"key":"sheet_reference_prefix","label":"formula before reference","type":"raw","default":"="},
            ]
            self._lcd_begin_form(f"SHEET insert {source}",fields,"sheet_grab")
            return
        if tool in {"Fill value","Fill formula"}:
            fields=[
                self._lcd_choice_field("sheet_target_column","end column",{1:"A",2:"B",3:"C",4:"D",5:"E"}),
                self._lcd_number_field("sheet_target_row","end row",1,integer=True,minimum=1,maximum=45),
                {"key":"sheet_fill_text","label":"value" if tool=="Fill value" else "=formula","type":"raw","default":""},
            ]
            self._lcd_begin_form("SHEET "+tool,fields,"sheet_fill_value" if tool=="Fill value" else "sheet_fill_formula")
            return
        if tool=="Recalculate":
            count=len(self.sheet.recalculate()); self._lcd_sheet_return(f"Recalculated {count} cells")
            return
        if tool=="Free space":
            self._lcd_show_results("SHEET",[f"Free space = {self.sheet.free_space()} bytes"])
            return
        self._lcd_begin_form("SHEET delete all",[self._lcd_choice_field("sheet_confirm","confirm",{1:"Cancel",2:"Delete all"},"Cancel")],"sheet_delete_all")

    def _lcd_sheet_target_address(self):
        values=self._lcd_flow["values"]
        return f"{values['sheet_target_column']}{values['sheet_target_row']}"

    def _lcd_run_sheet_copy(self):
        source=self._lcd_sheet_address(); destination=self._lcd_sheet_target_address()
        self.sheet.copy(source,destination)
        self._lcd_sheet_return(f"Copied {source} → {destination}")

    def _lcd_run_sheet_cut(self):
        source=self._lcd_sheet_address(); destination=self._lcd_sheet_target_address()
        self.sheet.cut(source,destination)
        self._lcd_sheet_return(f"Cut {source} → {destination}")

    def _lcd_run_sheet_grab(self):
        """Insert the selected source-cell reference into a destination formula.

        The former popup workspace called this feature "Grab".  Making both
        addresses and the expression prefix explicit works on the calculator
        LCD and prevents accidental self-references while retaining its
        formula-building purpose.
        """
        source=self._lcd_sheet_address(); destination=self._lcd_sheet_target_address()
        if source==destination:
            raise CalculatorError("Argument ERROR: reference destination must be different from the source")
        prefix=self._lcd_flow["values"]["sheet_reference_prefix"]
        if not prefix.startswith("="):
            raise CalculatorError("Syntax ERROR: formula before reference must start with =")
        self.sheet.set(destination,prefix+source)
        self._lcd_sheet_return(f"Inserted {source} into {destination}")

    def _lcd_run_sheet_fill_value(self):
        source=self._lcd_sheet_address(); destination=self._lcd_sheet_target_address()
        self.sheet.fill_value(source,destination,self._lcd_flow["values"]["sheet_fill_text"])
        self._lcd_sheet_return(f"Filled {source}:{destination}")

    def _lcd_run_sheet_fill_formula(self):
        source=self._lcd_sheet_address(); destination=self._lcd_sheet_target_address(); formula=self._lcd_flow["values"]["sheet_fill_text"]
        if not formula.startswith("="):
            raise CalculatorError("Syntax ERROR: formula must start with =")
        self.sheet.fill_formula(source,destination,formula)
        self._lcd_sheet_return(f"Filled {source}:{destination}")

    def _lcd_run_sheet_delete_all(self):
        if self._lcd_flow["values"]["sheet_confirm"]=="Delete all":
            self.sheet.delete_all()
            self._lcd_sheet_return("Spreadsheet cleared")
        else:
            self._lcd_sheet_return("Delete all cancelled")

    def consume(self): self.shift=False; self.alpha=False; self.status_refresh()
    def remember(self): self.undo.append(self.expr.get()); self.undo=self.undo[-50:]

    def cancel_template(self):
        self.template_kind=None; self.template_fields={}; self.template_order=[]; self.template_index=0; self.template_cursors={}
        try:
            if getattr(self,"skin_mode",False):
                self.template_canvas.place_forget()
                # restore normal LCD entry/result positions
                sx1,sy1=self._sp(40),self._sp(128); sx2=self._sp(435)
                self.expr.place(x=sx1+self._sp(7),y=sy1+self._sp(34),width=(sx2-sx1)-self._sp(14),height=self._sp(51))
                self.result.place(x=sx1+self._sp(7),y=sy1+self._sp(89),width=(sx2-sx1)-self._sp(14),height=self._sp(58))
            else:
                self.template_canvas.pack_forget()
                if not self.expr.winfo_ismapped():
                    self.expr.pack(fill="x",padx=7,pady=(2,2),ipady=5,before=self.result)
            self.expr.selection_clear()
        except Exception:
            pass

    def insert(self,s):
        if self._history_lcd_active():
            self.consume()
            return
        if self.template_kind:
            self.template_insert(s); self.consume(); return
        flow=self.__dict__.get("_lcd_flow")
        if flow and flow.get("phase")=="sheet" and flow.get("sheet_phase")=="browse":
            flow["editing"]=True
        self._lcd_prepare_direct_entry()
        self.remember(); pos=self.expr.index(tk.INSERT)
        if self.overwrite and pos<len(self.expr.get()): self.expr.delete(pos,pos+len(s))
        self.expr.insert(pos,s); self.consume()

    def set_expr(self,s):
        if not self._template_rendering:self.cancel_template()
        flow=self.__dict__.get("_lcd_flow")
        if flow and flow.get("phase")=="form":
            flow["field_armed"]=False
        self.expr.delete(0,tk.END); self.expr.insert(0,s)

    def show(self,x,approx=False): self.result.config(text=self.core.format_result(x,approximate=approx))

    def _clear_modifiers(self):
        self.shift=False
        self.alpha=False
        with suppress(AttributeError, RecursionError, tk.TclError):
            self.status_refresh()

    def _clear_active_input_for_error(self):
        """Clear only the active entry, preserving its current calculator mode."""
        flow=self.__dict__.get("_lcd_flow")
        if flow and flow.get("phase")=="form":
            spec=self._lcd_current_spec()
            if spec is not None:
                flow.setdefault("draft",{})[spec["key"]]=""
                flow["field_armed"]=False
        elif getattr(self,"template_kind",None):
            try:
                key=self._active_template_field()
                self.template_fields[key]=""
                self.template_cursors[key]=0
                self.render_template()
                return
            except (AttributeError, KeyError, RecursionError, tk.TclError):
                pass
        with suppress(AttributeError, RecursionError, tk.TclError):
            self.set_expr("")

    def err(self,e,*,clear_input=True):
        """Render calculator errors on the LCD; never open a popup."""
        if isinstance(e,CalculationTimeout):
            message="Math ERROR: calculation timed out"
        elif isinstance(e,(CalculatorError,str)):
            message=self._format_error_message(e)
        else:
            LOGGER.error("Unexpected calculator failure", exc_info=(type(e),e,e.__traceback__))
            message="Internal ERROR"
        if clear_input:
            self._clear_active_input_for_error()
        self._clear_modifiers()
        self._lcd_message(message)

    def shift_key(self): self.shift=not self.shift; self.alpha=False; self.status_refresh()
    def alpha_key(self): self.alpha=not self.alpha; self.shift=False; self.status_refresh()

    def _active_template_field(self):
        if not self.template_kind:return None
        return self.template_order[self.template_index]

    def move(self,d):
        """◀/▶ şablon alanları arasında zıplamaz; aktif metnin içinde gezer."""
        if self._history_lcd_active():
            return
        if self.template_kind:
            key=self._active_template_field()
            text=self.template_fields.get(key,"")
            cur=self.template_cursors.get(key,len(text))
            self.template_cursors[key]=max(0,min(len(text),cur+d))
            self.render_template(); return
        if self._lcd_move(d):
            return
        self.expr.icursor(max(0,min(len(self.expr.get()),self.expr.index(tk.INSERT)+d)))

    def vertical_move(self,d):
        if self._lcd_vertical_move(d):
            return
        if self.template_kind=="integral":
            cur=self._active_template_field()
            # Dikey geometri: üst ↔ gövde ↔ alt. Sağ/sol hiçbir zaman sınır seçmez.
            nxt=("body" if cur=="lower" else "upper") if d<0 else ("body" if cur=="upper" else "lower")
            self.template_index=self.template_order.index(nxt)
            self.render_template(); return
        if self.template_kind=="derivative":
            cur=self._active_template_field()
            # Türevde ▲/▼ fonksiyon ile x=a değerlendirme noktası arasında geçer.
            nxt="body" if (d<0 or cur=="point") else "point"
            self.template_index=self.template_order.index(nxt)
            self.render_template(); return
        self.history_move(d)

    def _template_keypress(self,event):
        if not self.template_kind:return None
        if event.keysym in ("Left","Right"):
            self.move(-1 if event.keysym=="Left" else 1); return "break"
        if event.keysym in ("Up","Down"):
            self.vertical_move(-1 if event.keysym=="Up" else 1); return "break"
        if event.keysym=="BackSpace":
            self.template_backspace(delete_forward=False); return "break"
        if event.keysym=="Delete":
            self.template_backspace(delete_forward=True); return "break"
        if event.keysym in ("Return","KP_Enter"):
            self.equals(); return "break"
        if event.keysym=="Escape":
            self.cancel_template(); self.set_expr(""); return "break"
        if event.keysym=="Tab":
            self.template_move(-1 if (event.state & 1) else 1); return "break"
        if event.state & 0x4:return "break"
        if event.char and event.char.isprintable():
            token=self._keyboard_character_token(event.char)
            if token is not None:
                self.template_insert(token)
            return "break"
        return "break"

    def start_integral_template(self):
        self._reset_lcd_flow()
        current=self.expr.get().strip() if not self.template_kind else ""
        # Keep the familiar calculator convention (``dx``) in every mode.
        # Complex integration accepts any single-letter variable, so forcing
        # ``dz`` here made a normal ``sqrt(ln(x))`` entry fail even though the
        # user had no practical way to select ``x`` in the template.
        variable="x"
        self.template_kind="integral"
        self.template_fields={"lower":"","upper":"","body":current,"var":variable}
        # The differential is an editable template field.  Tab reaches it
        # after the lower bound, which also lets complex-analysis users choose
        # ``z`` deliberately rather than treating it as a hidden requirement.
        self.template_order=["body","upper","lower","var"]
        self.template_index=self.template_order.index("body")
        self.template_cursors={k:len(v) for k,v in self.template_fields.items()}
        self.render_template()
        mode_hint="Complex" if self.mode=="Complex" else self.core.settings.angle_unit
        self.result.config(text=f"∫  {mode_hint}  •  ▲ upper  •  ▼ lower  •  TAB: d-variable")

    def start_derivative_template(self):
        self._reset_lcd_flow()
        current=self.expr.get().strip() if not self.template_kind else ""
        self.template_kind="derivative"
        self.template_fields={"body":current,"var":"x","point":""}
        self.template_order=["body","point"]
        self.template_index=self.template_order.index("body")
        self.template_cursors={k:len(v) for k,v in self.template_fields.items()}
        self.render_template()
        self.result.config(text="d/dx  RAD  •  ▲ function  •  ▼ x=a")

    def _canvas_caret_x(self, text, cursor, font_desc, start_x):
        try:
            font=tkfont.Font(font=font_desc)
            return start_x+font.measure(text[:cursor])
        except Exception:
            return start_x+cursor*10

    def _template_text_view(self,text,cursor,font_desc,max_width):
        """Return a cursor-visible one-line slice for a constrained canvas field."""
        text=text or ""
        cursor=max(0,min(len(text),cursor))
        if not text:
            return "□",0
        try:
            font=tkfont.Font(font=font_desc)
            measure=font.measure
        except Exception:
            measure=lambda value:len(value)*10
        if max_width is None or measure(text)<=max_width:
            return text,measure(text[:cursor])

        ellipsis="…"
        # Keep the caret just to the right of centre where possible, then use
        # the remaining width for the expression after it.
        start=0
        before_budget=max(1,int(max_width*0.55))
        while start<cursor and measure((ellipsis if start else "")+text[start:cursor])>before_budget:
            start+=1
        end=len(text)
        def display_width():
            return measure((ellipsis if start else "")+text[start:end]+(ellipsis if end<len(text) else ""))
        while end>cursor and display_width()>max_width:
            end-=1
        while start<cursor and display_width()>max_width:
            start+=1
        prefix=ellipsis if start else ""
        suffix=ellipsis if end<len(text) else ""
        shown=prefix+text[start:end]+suffix
        return shown,measure(prefix+text[start:cursor])

    def _draw_edit_text(self,c,key,text,x,y,font_desc,box=None,anchor="w",max_text_width=None):
        active=self._active_template_field()==key
        cursor=max(0,min(len(text),self.template_cursors.get(key,len(text))))
        shown,caret_offset=self._template_text_view(text,cursor,font_desc,max_text_width)
        if box and active:
            c.create_rectangle(*box,outline="#222222",width=max(1,int(round(self._sp(2)))))
        c.create_text(x,y,text=shown,font=font_desc,anchor=anchor,fill="#111111")
        if active:
            cx=x+caret_offset
            half=self._sp(13)
            c.create_line(cx,y-half,cx,y+half,fill="#111111",width=max(1,int(round(self._sp(2)))))

    def render_template(self):
        if not self.template_kind:
            return
        f=self.template_fields
        S=self._sp

        if getattr(self,"skin_mode",False):
            with suppress(Exception):
                self.expr.place_forget()
            sx1,sy1=S(40),S(128); sx2=S(435)
            self.template_canvas.place(
                x=sx1+S(7), y=sy1+S(30),
                width=(sx2-sx1)-S(14), height=S(92)
            )
            self.result.place(
                x=sx1+S(7), y=sy1+S(126),
                width=(sx2-sx1)-S(14), height=S(23)
            )
        else:
            with suppress(Exception):
                self.expr.pack_forget()
            if not self.template_canvas.winfo_ismapped():
                self.template_canvas.pack(fill="x",padx=7,pady=(1,2),before=self.result)

        c=self.template_canvas
        c.delete("all")
        # Work directly in physical scaled pixels so the 100% design is preserved.
        # In skin mode the template canvas occupies the LCD's inner width
        # (395 - 14 = 381 logical pixels), not the full 430 px LCD panel.
        # Using the panel width positions the differential variable outside
        # the canvas, clipping the final "x" in "dx".
        # The canvas is placed at the LCD's 381 px inner width in skin mode.
        # Derive every integral position from that same logical width so a UI
        # scale change keeps the full differential visible.
        w=int(round(S(381))) if getattr(self,"skin_mode",False) else max(c.winfo_width(),int(round(S(480))))

        if self.template_kind=="integral":
            c.config(height=max(1,int(round(S(72)))))
            c.create_text(S(18),S(36),text="∫",font=("Cambria Math",self._fp(46)),anchor="w",fill="#111111")
            self._draw_edit_text(
                c,"upper",f.get("upper",""),S(46),S(13),
                ("Consolas",self._fp(12),"bold"),
                (S(40),S(2),S(139),S(25))
            )
            self._draw_edit_text(
                c,"lower",f.get("lower",""),S(46),S(59),
                ("Consolas",self._fp(12),"bold"),
                (S(40),S(47),S(139),S(70))
            )

            body_x=S(150)
            close_x=w-S(88)
            body_right=max(body_x+S(12),close_x-S(7))
            self._draw_edit_text(
                c,"body",f.get("body",""),body_x,S(36),
                ("Consolas",self._fp(19)),
                (S(145),S(21),body_right,S(52)),
                max_text_width=body_right-body_x
            )
            differential_x=min(close_x+max(1,S(1)),w-S(35))
            c.create_text(differential_x,S(36),text="d",font=("Consolas",self._fp(17)),anchor="w",fill="#111111")
            var_x=min(differential_x+S(20),w-S(35))
            self._draw_edit_text(
                c,"var",f.get("var","") or "x",var_x,S(36),
                ("Consolas",self._fp(17),"bold"),
                (min(differential_x+S(15),w-S(55)),S(22),w-S(7),S(52))
            )
        else:
            c.config(height=max(1,int(round(S(62)))))
            var=f.get("var") or "x"
            c.create_text(S(12),S(31),text=f"d/d{var} ",font=("Consolas",self._fp(17),"bold"),anchor="w",fill="#111111")
            body_x=S(70)
            close_x=w-S(138)
            body_right=max(body_x+S(12),close_x-S(7))
            self._draw_edit_text(
                c,"body",f.get("body",""),body_x,S(31),
                ("Consolas",self._fp(18)),
                (S(64),S(16),body_right,S(48)),
                max_text_width=body_right-body_x
            )
            c.create_text(close_x,S(31),text=f"| {var}=",font=("Consolas",self._fp(16)),anchor="w",fill="#111111")
            point_x=min(close_x+S(52),w-S(56))
            self._draw_edit_text(
                c,"point",f.get("point",""),point_x,S(31),
                ("Consolas",self._fp(16),"bold"),
                (point_x-S(4),S(17),w-S(8),S(48))
            )
            if self._active_template_field()=="var":
                c.create_rectangle(
                    w-S(70),S(1),w-S(8),S(16),
                    outline="#222222",width=max(1,int(round(S(1))))
                )
            c.create_text(w-S(12),S(8),text=f"d/d{var}",font=("Consolas",self._fp(9)),anchor="e",fill="#333333")
        c.focus_set()

    def template_move(self,d):
        if not self.template_kind:return
        self.template_index=(self.template_index+d)%len(self.template_order)
        key=self._active_template_field()
        self.template_cursors.setdefault(key,len(self.template_fields.get(key,"")))
        self.render_template()

    def template_insert(self,s):
        if not self.template_kind:return
        key=self._active_template_field()
        if key=="var":
            candidate=s.strip()
            if candidate and candidate[-1].isalpha():
                self.template_fields[key]=candidate[-1]
                self.template_cursors[key]=1
        else:
            text=self.template_fields.get(key,"")
            cur=max(0,min(len(text),self.template_cursors.get(key,len(text))))
            self.template_fields[key]=text[:cur]+s+text[cur:]
            self.template_cursors[key]=cur+len(s)
        self.render_template()

    def template_backspace(self,delete_forward=False):
        if not self.template_kind:return
        key=self._active_template_field()
        if key=="var":
            self.template_fields[key]="x"; self.template_cursors[key]=1; self.render_template(); return
        text=self.template_fields.get(key,"")
        cur=max(0,min(len(text),self.template_cursors.get(key,len(text))))
        if delete_forward:
            if cur<len(text): text=text[:cur]+text[cur+1:]
        else:
            if cur>0:
                text=text[:cur-1]+text[cur:]; cur-=1
        self.template_fields[key]=text; self.template_cursors[key]=cur
        self.render_template()

    @staticmethod
    def _repair_integral_body(text):
        """Remove only trailing unmatched ``)`` copied from the integral shell."""
        original=str(text).strip()

        def balanced(candidate):
            depth=0
            for character in candidate:
                if character=="(": depth+=1
                elif character==")":
                    depth-=1
                    if depth<0: return False
            return depth==0

        if balanced(original):
            return original
        repaired=original
        while repaired.endswith(")"):
            repaired=repaired[:-1].rstrip()
            if balanced(repaired):
                return repaired
        return original

    def evaluate_template(self):
        kind=self.template_kind; f=dict(self.template_fields)
        if kind=="integral":
            body=self._repair_integral_body(f.get("body", "")); var=(f.get("var") or "x").strip()
            self.template_fields["body"]=body
            self.template_cursors["body"]=min(self.template_cursors.get("body",len(body)),len(body))
            lo=f.get("lower","").strip(); hi=f.get("upper","").strip()
            if not body: raise CalculatorError("Syntax ERROR: Integral function is empty")
            if bool(lo)!=bool(hi): raise CalculatorError("Argument ERROR: Enter both lower and upper bounds, or leave both blank")
            if lo and hi:
                operation="complex_definite_integral" if self.mode=="Complex" else "definite_integral"
                self._run_background_calculation(
                    operation, (body,lo,hi,var),
                    lambda r:(self.result.config(text=f"∫={self.core.format_result(r,True)}"),self.cancel_template()),
                )
            else:
                self._run_background_calculation(
                    "symbolic_integral", (body,var),
                    lambda r:(self.result.config(text=f"{self.core.format_result(r)} + C"),self.cancel_template()),
                )
            return
        elif kind=="derivative":
            body=f.get("body","").strip(); var=(f.get("var") or "x").strip(); point=f.get("point","").strip()
            if not body: raise CalculatorError("Syntax ERROR: Derivative function is empty")
            if point:
                self._run_background_calculation("derivative", (body,point,var), lambda r:(self.result.config(text=f"d/d{var}={self.core.format_result(r,True)}"), self.cancel_template()))
            else:
                self._run_background_calculation("symbolic_derivative", (body,var), lambda r:(self.result.config(text=self.core.format_result(r)), self.cancel_template()))
        if not self.__dict__.get("_calculation_busy",False): self.cancel_template()

    def history_move(self,d):
        if not self.core.history:return
        self.history_pos=max(0,min(len(self.core.history)-1,self.history_pos+d))
        expression,result=self.core.history[self.history_pos]
        self.set_expr(expression)
        self.result.config(text=result)

    def show_history(self):
        self._start_lcd_flow("History")
        self.consume()

    def del_key(self):
        if self._history_lcd_active():
            self.consume()
            return
        if self.template_kind:
            self.template_backspace(delete_forward=False); self.consume(); return
        flow=self.__dict__.get("_lcd_flow")
        if flow and flow.get("phase")=="sheet" and flow.get("sheet_phase")=="browse":
            flow["editing"]=True
        if self.shift: self.overwrite=not self.overwrite; self.consume(); return
        if self.alpha:
            if self.undo: cur=self.expr.get(); prev=self.undo.pop(); self.undo.append(cur); self.set_expr(prev)
            self.consume(); return
        self._lcd_prepare_direct_entry()
        p=self.expr.index(tk.INSERT)
        if p>0: self.remember(); self.expr.delete(p-1,p)

    def _reset_active_mode_after_ac(self):
        """Return to the active mode's clean starting screen after AC/cancel."""
        self.cancel_template()
        self._reset_lcd_flow()
        self.set_expr("")
        if self.mode in {"Calculate","Complex"}:
            self.result.config(text="0")
        elif self.mode in self.LCD_WORKSPACE_MODES:
            self._start_lcd_flow(self.mode)
        else:
            self.result.config(text=self.MODE_HINTS.get(self.mode,""))
        self.consume()

    def ac_key(self):
        # Cancellation deliberately wins over SHIFT (whose normal AC action is
        # close) and over every template/LCD flow while a calculation runs.
        if self.__dict__.get("_calculation_busy",False):
            self.calculation_controller.cancel()
            self._reset_active_mode_after_ac()
            return
        if self.shift: self._on_close(); return
        flow=self.__dict__.get("_lcd_flow")
        if flow:
            self._reset_active_mode_after_ac()
            return
        self._reset_active_mode_after_ac()
    def _restart_application(self):
        controller = self.__dict__.get("calculation_controller")
        # Unlike normal AC cancellation, a restart immediately destroys the
        # Tk scheduler.  ``close`` terminates and reaps a live worker before
        # that happens, whereas ``cancel`` defers cleanup through ``after``.
        if controller: controller.close()
        self.save_settings_file(False)
        restart_application()
        # ``execv`` normally never returns. This keeps injected test/fallback
        # launchers from leaving the old Tk instance active.
        self.destroy()

    def on_key(self): self._restart_application()

    def menu_key(self):
        if self._history_lcd_active():
            self.consume()
            return
        if self.shift:
            self.consume()
            self.setup_dialog()
            return
        m=tk.Menu(self,tearoff=0)
        for x in self.MODES:
            m.add_command(label=x,command=lambda n=x:self.select_mode(n))
        m.add_separator()
        m.add_command(label="History",command=self.show_history)
        m.add_command(label="Setup...",command=self.setup_dialog)
        try:
            m.tk_popup(self.winfo_pointerx(),self.winfo_pointery())
        finally:
            m.grab_release()

    def select_mode(self,m,w=None):
        if m!=self.mode:
            self.cancel_template()
            App._reset_lcd_flow(self)
        elif self.__dict__.get("_lcd_flow") is not None:
            App._reset_lcd_flow(self)
        self.mode=m; self.consume(); self.status_refresh();
        self.result.config(text=self.MODE_HINTS[m])
        if w:w.destroy()
        if m in App.LCD_WORKSPACE_MODES:
            self._start_lcd_flow(m)

    def setup_dialog(self):
        w=tk.Toplevel(self); w.title("SETUP"); w.geometry("460x775"); w.resizable(False,False)
        vars={}
        def combo(label,vals,cur,attr):
            f=ttk.Frame(w); f.pack(fill="x",padx=12,pady=3)
            ttk.Label(f,text=label,width=22).pack(side="left")
            v=tk.StringVar(value=cur); vars[attr]=v
            ttk.Combobox(f,textvariable=v,values=vals,state="readonly").pack(side="left",fill="x",expand=True)

        s=self.core.settings
        combo("Input / Output",["MathI/MathO","MathI/DecimalO","LineI/LineO","LineI/DecimalO"],s.input_output,"input_output")
        combo("Angle Unit",["DEG","RAD","GRA"],s.angle_unit,"angle_unit")
        combo("Number Format",["Norm","Fix","Sci"],s.number_format,"number_format")
        combo("Number Digits",[str(i) for i in range(10)],str(s.number_digits),"number_digits")
        combo("Engineer Symbol",["On","Off"],"On" if s.engineer_symbol else "Off","engineer_symbol")
        combo("Fraction Result",["d/c","a b/c"],s.fraction_result,"fraction_result")
        combo("Complex",["a+bi","r∠θ"],s.complex_format,"complex_format")
        combo("Statistics Frequency",["On","Off"],"On" if s.statistics_freq else "Off","statistics_freq")
        combo("Spreadsheet Auto Calc",["On","Off"],"On" if s.spreadsheet_auto_calc else "Off","spreadsheet_auto_calc")
        combo("Spreadsheet Show Cell",["Formula","Value"],s.spreadsheet_show_cell,"spreadsheet_show_cell")
        combo("Equation Complex",["On","Off"],"On" if s.equation_complex else "Off","equation_complex")
        combo("Table",["f(x)","f(x),g(x)"],"f(x),g(x)" if s.table_two_functions else "f(x)","table_two_functions")
        combo("Decimal Mark",["Dot","Comma"],s.decimal_mark,"decimal_mark")
        combo("Digit Separator",["On","Off"],"On" if s.digit_separator else "Off","digit_separator")
        combo("MultiLine Font",["Normal","Small"],s.multiline_font,"multiline_font")
        combo("Scientific Constants",list(CONSTANTS_DATASET_LABELS),s.constant_dataset,"constant_dataset")
        combo("Calculator Skin",list(self.SKINS),self.skin_name,"skin_name")
        combo("UI Scale",[str(value) for value in reversed(self.UI_SCALES)],str(self.ui_scale),"ui_scale")

        def save():
            original_settings=copy.copy(s)
            original_scale=self.ui_scale
            original_skin=self.skin_name
            new_scale=self.ui_scale
            for k,v in vars.items():
                val=v.get()
                if k=="ui_scale":
                    new_scale=int(val); continue
                if k=="skin_name":
                    self.skin_name=self._validated_skin_name(val); continue
                if k in self.BOOLEAN_SETTINGS:
                    val=self._coerce_boolean_setting(k,val)
                elif k=="table_two_functions":
                    val=val=="f(x),g(x)"
                elif k=="number_digits":
                    val=int(val)
                setattr(s,k,val)
            self.ui_scale=self._fit_ui_scale_to_display(new_scale)
            if not self.save_settings_file(False):
                self.core.settings=original_settings
                self.ui_scale=original_scale
                self.skin_name=original_skin
                self.err(CalculatorError("Settings ERROR: save failed"), clear_input=False)
                return
            w.destroy()
            self._rebuild_scaled_ui()
            self._lcd_message("Settings saved")

        def reset():
            if self.reset_app_settings():
                w.destroy()

        def clear_history():
            if messagebox.askyesno(
                "Clear History",
                "Delete the saved calculation history? This cannot be undone.",
                parent=w,
            ):
                self.clear_calculation_history()

        buttons=ttk.Frame(w); buttons.pack(fill="x",padx=12,pady=12)
        ttk.Button(buttons,text="Save",command=save).pack(side="left",expand=True,fill="x",padx=(0,4))
        ttk.Button(buttons,text="Clear History",command=clear_history).pack(side="left",expand=True,fill="x",padx=4)
        ttk.Button(buttons,text="Reset to Defaults",command=reset).pack(side="left",expand=True,fill="x",padx=(4,0))

    def _left_context(self):
        if self.template_kind:
            key=self._active_template_field(); txt=self.template_fields.get(key,"")
            pos=max(0,min(len(txt),self.template_cursors.get(key,len(txt))))
            return txt[:pos]
        txt=self.expr.get()
        try: pos=self.expr.index(tk.INSERT)
        except Exception: pos=len(txt)
        return txt[:pos]

    def _insert_function_token(self, token):
        left=self._left_context(); prefix=""
        if left:
            last=left[-1]
            if last==")" or last.isdigit() or last in ("x","y","π","e"):
                prefix="×"
        self.insert(prefix+token)

    def num_key(self,n):
        if self.shift and n=="7": self.consume(); self.constants_dialog(); return
        if self.shift and n=="8": self.consume(); self.conversions_dialog(); return
        if self.shift and n=="9": self.consume(); self.reset_dialog(); return
        self.insert(n)
    def x_key(self):
        if self._history_lcd_active():
            self.consume()
            return
        if self.shift: self.consume(); self.sum_dialog(); return
        self.insert("x")
    def fraction_key(self): self.insert(" + 1/2" if self.shift else "/")
    def sqrt_key(self): self._insert_function_token("cbrt(" if self.shift else "sqrt(")
    def square_key(self):
        if self.mode=="Base-N": self.base=10; self.consume(); self.status_refresh(); return
        self.insert("^3" if self.shift else "^2")
    def power_key(self):
        if self.mode=="Base-N": self.base=16; self.consume(); self.status_refresh(); return
        if self.shift:
            n=simpledialog.askstring("nth Root","Root degree n =",parent=self)
            if n:self.insert(f"^(1/({n}))")
            else:self.consume()
        else:self.insert("^")
    def log_key(self):
        if self.mode=="Base-N": self.base=2; self.consume(); self.status_refresh(); return
        self._insert_function_token("10^(" if self.shift else "log(")
    def ln_key(self):
        if self.mode=="Base-N": self.base=8; self.consume(); self.status_refresh(); return
        self._insert_function_token("e^(" if self.shift else "ln(")
    def neg_key(self):
        if self.alpha:self.insert("A"); return
        self.insert("log(" if self.shift else "-")
    def dms_key(self):
        if self.alpha:self.insert("B"); return
        if self.shift:
            try:
                f=self.core.prime_factorization(self.core.ans); self.result.config(text=" × ".join(f"{p}^{e}" if e>1 else str(p) for p,e in f.items()))
            except Exception as e:self.err(e)
            self.consume(); return
        self.dms_dialog()
    def inv_key(self):
        if self.alpha:self.insert("C"); return
        self.insert("factorial(" if self.shift else "^(-1)")
    def trig_key(self,n):
        if self.alpha:self.insert({"sin":"D","cos":"E","tan":"F"}[n]); return
        self._insert_function_token(("a"+n if self.shift else n)+"(")
    def sto_key(self):
        if self.shift:
            self.consume(); self.recall_dialog(); return
        name=simpledialog.askstring("STO","Memory: A,B,C,D,E,F,M,x,y",parent=self)
        if name:
            try:self.core.store(name.strip(),self.core.ans); self.result.config(text=f"{name}={self.core.format_result(self.core.ans)}")
            except Exception as e:self.err(e)
        self.consume()
    def eng_key(self):
        if self.mode=="Complex": self.insert("∠" if self.shift else "i"); return
        try:
            # Engineering notation is normalized to a multiple-of-three
            # exponent; applying an extra group made normal ENG output use a
            # mantissa below one (for example 1234 -> 0.001234×10^6).
            v=float(sp.N(self.core.ans)); exp=0 if v==0 else int(math.floor(math.log10(abs(v))/3)*3); self.result.config(text=f"{v/(10**exp):.10g}×10^{exp}")
        except Exception as e:self.err(e)
        self.consume()
    def lparen_key(self):
        if self.shift: self._insert_function_token("Abs(")
        else: self.insert("(")
    def rparen_key(self):
        if self.alpha:self.insert("x"); return
        self.insert("," if self.shift else ")")
    def sd_key(self):
        if self.alpha:self.insert("y"); return
        try:
            v=sp.nsimplify(self.core.ans)
            if self.shift and isinstance(v,sp.Rational):
                whole=int(v); rem=abs(v-whole); self.result.config(text=f"{whole} {rem.p}/{rem.q}" if rem else str(whole))
            else:
                cur=self.result.cget("text")
                if "/" in cur or "√" in cur or "pi" in cur: self.result.config(text=self.core.format_result(sp.N(v,15),True))
                else:self.result.config(text=self.core.format_result(v,False))
        except Exception as e:self.err(e)
        self.consume()
    def mplus_key(self):
        if self.alpha:self.insert("M"); return
        try:v=self.core.m_minus() if self.shift else self.core.m_plus(); self.result.config(text=f"M={self.core.format_result(v)}")
        except Exception as e:self.err(e)
        self.consume()
    def mul_key(self):
        if self.shift:
            self.consume(); self.comb_dialog("nPr"); return
        self.insert("×")
    def div_key(self):
        if self.shift:
            self.consume(); self.comb_dialog("nCr"); return
        self.insert("÷")
    def comb_dialog(self,kind):
        n=simpledialog.askinteger(kind,"n =",parent=self); r=simpledialog.askinteger(kind,"r =",parent=self)
        if n is None or r is None:return
        try:
            expr=f"{kind}({n},{r})"; self.set_expr(expr); self.show(self.core.evaluate(expr)); self._persist_calculation_history()
        except Exception as e:self.err(e)
    def plus_key(self):
        if self.shift:self.consume(); self.pol_dialog(); return
        self.insert("+")
    def minus_key(self):
        if self.shift:self.consume(); self.rec_dialog(); return
        self.insert("−")
    def dot_key(self):
        if self.alpha:
            a=simpledialog.askinteger("RanInt#","Lower bound",parent=self); b=simpledialog.askinteger("RanInt#","Upper bound",parent=self)
            if a is not None and b is not None:
                try:self.insert(str(self.core.random_int(a,b)))
                except Exception as error:self.err(error)
            else:self.consume()
            return
        if self.shift:self.insert(str(self.core.random_number())); return
        self.insert(".")
    def sci_key(self):
        if self.alpha:self.insert("e"); return
        self.insert("π" if self.shift else "×10^")
    def ans_key(self): self.insert("%" if self.shift else "Ans")

    def equals(self):
        if self.__dict__.get("_calculation_busy",False):
            return
        if self._history_lcd_active():
            self.consume()
            return
        if self._lcd_flow_active():
            self.shift=False; self.status_refresh(); self._lcd_submit(); self.consume(); return
        if self.shift:
            self.shift=False; self.status_refresh(); self.approx(); return
        if self.template_kind:
            try:self.evaluate_template()
            except Exception as e:self.err(e)
            self.consume(); return
        text=self.expr.get().strip()
        if not text:return
        if self.mode=="Base-N":
            try:
                v=self.core.evaluate_base(text,self.base); self.core.ans=sp.Integer(v); self.result.config(text=self.core.format_base(v,self.base))
            except Exception as e:self.err(e)
            self.consume(); return
        if self.mode=="Complex":
            self._run_background_calculation("complex_eval",(text,),self.show)
            self.consume(); return
        self._run_background_calculation(
            "evaluate", (text,), lambda result: (self.show(result), setattr(self, "history_pos", max(0, len(self.core.history)-1))),
        )
        self.consume()
    def approx(self):
        self._run_background_calculation("evaluate", (self.expr.get(), False), lambda result:self.show(result,True))
        self.consume()

    def calc_key(self):
        if self._history_lcd_active():
            self.consume()
            return
        if self.alpha:self.insert("="); return
        if self.shift:self.consume(); self.solve_dialog(); return
        self.consume(); self.calc_dialog()
    def calc_dialog(self):
        text=self.expr.get().strip(); vars_found=[v for v in "ABCDEFMxy" if re.search(rf'(?<![A-Za-z]){v}(?![A-Za-z])',text)]
        vals={}
        for v in vars_found:
            x=simpledialog.askfloat("CALC",f"{v} =",initialvalue=float(self.core.memory[v]),parent=self)
            if x is None:return
            vals[v]=x
        if vars_found:
            self._run_background_calculation("evaluate_with_values",(text,vals),self.show)
        else:
            self._run_background_calculation("evaluate",(text,),self.show)
    def solve_dialog(self):
        if self.mode!="Calculate":self.err("SOLVE is available only in Calculate mode"); return
        if self.template_kind:
            self.err("Exit the integral/derivative template with AC before using SOLVE"); return
        eq=self.expr.get().strip()
        if not eq:self.err("Enter an equation"); return
        try: syms=self.core.equation_symbols(eq)
        except Exception as e:self.err(e); return
        if not syms:
            self.err("Variable ERROR: no variable to solve in the equation"); return
        initial="x" if "x" in syms else syms[0]
        if len(syms)==1:
            var=syms[0]
        else:
            var=simpledialog.askstring("SOLVE",f"Variable to solve ({', '.join(syms)}):",initialvalue=initial,parent=self)
            if not var:return
            var=var.strip()
            if var not in syms:self.err("Variable ERROR: selected variable is not in the equation"); return
        default_guess=float(sp.N(self.core.memory.get(var,0))) if var in self.core.memory else 0.0
        guess=simpledialog.askfloat("SOLVE",f"Initial guess for {var}",initialvalue=default_guess,parent=self)
        if guess is None:return
        known={}
        for name in syms:
            if name==var:continue
            default=float(sp.N(self.core.memory.get(name,0))) if name in self.core.memory else 0.0
            value=simpledialog.askfloat("SOLVE",f"{name} =",initialvalue=default,parent=self)
            if value is None:return
            known[name]=value
        self._run_background_calculation(
            "solve", (eq,var,guess,known),
            lambda result:self.result.config(text=f"{var}={result[0]:.12g}   L-R={result[1]:.4g}"),
        )

    def integral_key(self):
        if self._history_lcd_active():
            self.consume()
            return
        if self.alpha:self.insert(":"); return
        if self.shift:
            self.consume(); self.start_derivative_template(); return
        self.consume()
        if self.mode=="Calculate":
            self._start_lcd_flow("Integral")
            return
        if self.mode=="Complex":
            self._start_lcd_flow("Complex Integral")
            return
        self.start_integral_template()

    def integral_menu(self):
        """Compatibility entry point for callers of the former pop-up menu.

        Calculus choices now stay in the calculator LCD rather than opening a
        transient Tk menu or a chain of input windows.
        """
        self._start_lcd_flow("Integral")

    def sum_dialog(self):
        f=simpledialog.askstring("Σ","f(x)=",initialvalue=self.expr.get() or "x+1",parent=self); a=simpledialog.askstring("Σ","Lower=",initialvalue="1",parent=self); b=simpledialog.askstring("Σ","Upper=",initialvalue="5",parent=self)
        if None in (f,a,b):return
        self._run_background_calculation("summation", (f,a,b),lambda result:self.show(result))
    def pol_dialog(self):
        x=simpledialog.askfloat("Pol","x=",parent=self); y=simpledialog.askfloat("Pol","y=",parent=self)
        if x is not None and y is not None:
            r,t=self.core.pol(x,y); self.result.config(text=f"r={r:.12g}, θ={t:.12g}")
    def rec_dialog(self):
        r=simpledialog.askfloat("Rec","r=",parent=self); t=simpledialog.askfloat("Rec","θ=",parent=self)
        if r is not None and t is not None:
            x,y=self.core.rec(r,t); self.result.config(text=f"x={x:.12g}, y={y:.12g}")
    def dms_dialog(self):
        try:
            if self.expr.get().strip():
                x=float(self.core.evaluate(self.expr.get(),exact=False)); d,m,s=self.core.dms_from_decimal(x)
                degree_text="-0" if d==0 and math.copysign(1.0,float(d))<0 else str(int(d))
                self.result.config(text=f"{degree_text}° {m}′ {s:.8g}″")
            else:
                d=simpledialog.askfloat("DMS","Degrees",parent=self); m=simpledialog.askfloat("DMS","Minutes",parent=self); s=simpledialog.askfloat("DMS","Seconds",parent=self)
                if None not in (d,m,s): self.result.config(text=str(self.core.decimal_from_dms(d,m,s)))
        except Exception as e:self.err(e)
        self.consume()

    def optn_key(self):
        if self._lcd_flow_active():
            self._lcd_options(); self.consume(); return
        if self.shift: self.consume()
        menu=tk.Menu(self,tearoff=False)
        if self.mode=="Calculate":
            hyp=tk.Menu(menu,tearoff=False)
            for x in ["sinh","cosh","tanh","asinh","acosh","atanh"]: hyp.add_command(label=x,command=lambda n=x:self._insert_function_token(n+'('))
            menu.add_cascade(label="Hyperbolic Func",menu=hyp)
            ang=tk.Menu(menu,tearoff=False)
            for label,u in [("° Degree","DEG"),("r Radian","RAD"),("g Gradian","GRA")]: ang.add_command(label=label,command=lambda uu=u:self.set_angle(uu))
            menu.add_cascade(label="Angle Unit",menu=ang)
        elif self.mode=="Complex":
            for label,fn in [("Conjugate","conjugate("),("Argument","arg("),("Real Part","re("),("Imaginary Part","im(")]: menu.add_command(label=label,command=lambda f=fn:self.insert(f))
            menu.add_separator(); menu.add_command(label="Complex Calculus",command=lambda:self._start_lcd_flow("Complex Integral")); menu.add_separator(); menu.add_command(label="→r∠θ",command=self.complex_to_polar); menu.add_command(label="→a+bi",command=self.complex_from_polar)
        elif self.mode=="Base-N":
            for op in ["and","or","xor","xnor","Not","Neg"]: menu.add_command(label=op,command=lambda o=op:self.base_logic_dialog(o))
        else: menu.add_command(label=f"Open {self.mode} workspace",command=lambda:self.mode_workspace(self.mode))
        try:menu.tk_popup(self.winfo_pointerx(),self.winfo_pointery())
        finally:menu.grab_release(); self.consume()
    def set_angle(self,u): self.core.settings.angle_unit=u; self.status_refresh()
    def complex_to_polar(self):
        def show_polar(value):
            r,a=self.core.to_polar(complex(value))
            self.result.config(text=f"{r:.12g}∠{a:.12g}")
        self._run_background_calculation("complex_eval",(self.expr.get(),),show_polar)
    def complex_from_polar(self):
        r=simpledialog.askfloat("r∠θ","r=",parent=self); a=simpledialog.askfloat("r∠θ","θ=",parent=self)
        if r is not None and a is not None:self.result.config(text=self.core.format_result(self.core.from_polar(r,a)))
    def base_logic_dialog(self,op):
        try:
            a=self.core.evaluate_base(self.expr.get() or "0",self.base); b=None
            if op not in ("Not","Neg"):
                s=simpledialog.askstring(op,"Second value",parent=self)
                if s is None:return
                b=self.core.evaluate_base(s,self.base)
            r=self.core.base_operation(a,b,op); self.core.ans=sp.Integer(r); self.result.config(text=self.core.format_base(r,self.base))
        except Exception as e:self.err(e)

    def constants_dialog(self):
        dataset=self.core.settings.constant_dataset
        constants=constants_for_dataset(dataset)
        w=tk.Toplevel(self); w.title(f"CONST – {len(constants)} Scientific Constants"); lb=tk.Listbox(w,width=65,height=22); lb.pack(padx=8,pady=8,fill="both",expand=True)
        ttk.Label(w,text=dataset).pack(padx=8,pady=(6,0))
        keys=list(constants)
        for k in keys: lb.insert(tk.END,f"{k:10s}  {constants[k][0]}")
        def choose():
            if not lb.curselection():return
            k=keys[lb.curselection()[0]]; val=constants[k][1]; self.insert(f"({val:.15g})"); w.destroy()
        ttk.Button(w,text="Insert",command=choose).pack(pady=5)
    def conversions_dialog(self):
        w=tk.Toplevel(self); w.title("CONV – 40 Unit Conversions"); val=tk.StringVar(value=self.core.format_result(self.core.ans,True)); ttk.Entry(w,textvariable=val).pack(fill="x",padx=8,pady=4)
        lb=tk.Listbox(w,width=50,height=20); lb.pack(padx=8,pady=4,fill="both",expand=True); keys=list(CONVERSIONS)
        for k in keys:lb.insert(tk.END,k)
        def go():
            try:k=keys[lb.curselection()[0]]; r=self.core.convert(k,float(val.get().replace(',','.'))); self.core.ans=sp.Float(r); self.result.config(text=self.core.format_result(r,True)); w.destroy()
            except Exception as e:self.err(e)
        ttk.Button(w,text="Convert",command=go).pack(pady=5)
    def recall_dialog(self): messagebox.showinfo("RECALL","\n".join(f"{k} = {self.core.format_result(v)}" for k,v in self.core.memory.items()),parent=self)
    def reset_dialog(self):
        w=tk.Toplevel(self); w.title("RESET")
        ttk.Button(w,text="Setup Data",command=lambda:(setattr(self.core,'settings',type(self.core.settings)()),w.destroy(),self.status_refresh())).pack(fill="x",padx=10,pady=3)
        ttk.Button(w,text="Memory",command=lambda:(self.core.reset_memory(),w.destroy())).pack(fill="x",padx=10,pady=3)
        ttk.Button(w,text="Initialize All",command=lambda:(self.core.initialize_all(),self.sheet.delete_all(),w.destroy(),self.status_refresh())).pack(fill="x",padx=10,pady=3)

    def mode_workspace(self,m):
        if m in self.LCD_WORKSPACE_MODES:
            self._start_lcd_flow(m)
            return

    def _spreadsheet_display_value(self,address):
        if self.core.settings.spreadsheet_show_cell=="Formula":
            return self.sheet.cells.get(address,"")
        if address not in self.sheet.cells:
            return ""
        value=self.sheet.cache.get(address,"")
        return f"{value} *" if address in getattr(self.sheet,"dirty_cells",set()) else value
    def help_key(self):
        messagebox.showinfo("Quick help","MENU: 12 modes\nSHIFT+MENU: SETUP\nLCD modes: = next/run • ▲▼ field/result • ◀▶ choice/cell • OPTN action • AC restart\nALPHA+CALC: red =\nSHIFT+CALC: SOLVE\n∫: LCD calculus menu (definite, symbolic, multi/line/surface)\n  Select type with ◀▶, then enter variables and bounds\nSHIFT+∫: derivative template; empty point: symbolic\nEquation/Func: polynomial, simultaneous, or differential equation\nSHIFT+x: Σ\nSHIFT+7: CONST\nSHIFT+8: CONV\nSHIFT+9: RESET",parent=self)


def run_smoke_test() -> None:
    """Validate frozen runtime essentials without opening a Tk window."""
    frozen_base=getattr(sys,"_MEIPASS",None)
    asset_base=frozen_base or os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..","assets"))
    for asset in ("icons/app.ico",*App.SKINS.values()):
        asset_path=os.path.join(asset_base,asset)
        if not os.path.isfile(asset_path):
            raise RuntimeError(f"Required packaged asset is missing: {asset}")
    with Image.open(os.path.join(asset_base,"skins","skin_graphite.png")) as skin:
        if skin.size != (480,980):
            raise RuntimeError("Graphite skin has an unexpected size")
    # SciPy reaches this NumPy extension through a lazy import. Exercise it in
    # the packaged smoke check so a missing PyInstaller hidden import cannot
    # pass unnoticed.
    if not isinstance(np.random.default_rng(0).integers(1), np.integer):
        raise RuntimeError("NumPy random runtime smoke check failed")
    engine=ScientificCalculatorEngine()
    # SciPy loads sparse C extensions dynamically. Build-time collection and
    # this runtime assertion protect packaged startup from missing extensions.
    from scipy import sparse
    if sparse.csr_matrix([[1]]).nnz != 1:
        raise RuntimeError("SciPy sparse runtime smoke check failed")
    if engine.evaluate("2+2") != 4:
        raise RuntimeError("Calculation engine smoke check failed")


def main() -> None:
    multiprocessing.freeze_support()
    if "--smoke-test" in sys.argv:
        try:
            run_smoke_test()
        except Exception as exc:
            print(f"Scientific Calculator smoke test failed: {exc}",file=sys.stderr)
            raise SystemExit(1) from exc
    else:
        App().mainloop()


if __name__=='__main__':
    main()
