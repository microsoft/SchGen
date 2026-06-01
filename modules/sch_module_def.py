from pydantic import BaseModel
from dataclasses import dataclass
from enum import Enum

class PinInfo(BaseModel):
    pin_name: str
    pin_number: str
    x: float
    y: float
    orientation: str

class RelatedLibs(BaseModel):
    libs: list[str] = []

class rRelatedSymbols(BaseModel):
    """
    RelatedSymbols is a class that defines the properties of a related symbol in the schematic editor.
    It is used to define the properties of a related symbol in the schematic editor.
    """
    symbols: list[str] = []

class lib_sym(BaseModel):
    """
    lib_sym is a class that defines the properties of a library symbol in the schematic editor.
    It is used to define the properties of a library symbol in the schematic editor.
    """
    lib_name: str
    name: str

class SymbolInfo(BaseModel):
    name: str
    lib_name: str

class RelatedSymbols(BaseModel):
    """
    SymbolInfo is a class that defines the properties of a symbol in the schematic editor.
    """
    symbols: list[SymbolInfo] = []

class CircuitLabelType(Enum):
    """
    CircuitLabelType is an enumeration that defines the types of circuit labels.
    It is used to define the types of circuit labels in the schematic editor.
    """
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"
    POWER = "power"
    GND = "gnd"


class CircuitLabelDef(BaseModel):
    """
    CircuitLabelDef is a class that defines the properties of a schematic global label.
    """
    name: str
    label_type: CircuitLabelType

    # description for various specifics of the label, such as voltage, IO protocol, etc.
    description: str = ""


class CircuitModuleDef(BaseModel):
    """
    CircuitModuleDef is a class that defines the properties of a circuit module.
    It is used to define the properties of a circuit module in the schematic editor.
    """
    name: str
    
    # Functional description of the module
    description: str

    # Main IC/components used in the module
    main_IC: list[CircuitLabelDef] = []


class VisionFeedbackDef(BaseModel):
    """
    VisionFeedbackDef is a class that defines the feedback content from LLM for a schematic design.
    """
    explanation: str
    
    score: int = 0
    symbol_overlaps: list[str] = []
    wire_overlaps: list[str] = []
    missed_connections: list[str] = []
    
    errors: list[str] = []
    warnings: list[str] = []
    # suggestions: list[str] = []

class PCBFeedback(BaseModel):
    """
    PCBVisionFeedback is a class that defines the feedback content from LLM for a PCB layout design.
    """
    explanation: str
    
    score: int = 0
    footprint_overlaps: list[str] = []
    unconnected_net: list[str] = []
    
    errors: list[str] = []
    warnings: list[str] = []

class SymbolContextInfoDef(BaseModel):
    """
    SymbolContextInfoDef is a class that defines the context information of a symbol in the schematic editor.
    It is used to define the context information of a symbol in the schematic editor.
    """
    symbol_name: str
    lib_name: str
    Bounding_box: list[float] = []  # [x_min, y_min, x_max, y_max]
    pin_info: list[PinInfo] = []  # list of dict, each dict contains pin name, pin number, location, orientation, etc.

class NetlistFeedbackDef(BaseModel):
    """
    """
    explanation: str
    
    score: int = 0
    
    errors: list[str] = []
    warnings: list[str] = []
    # suggestions: list[str] = []

class LLMJudgeDef(BaseModel):
    """
    """
    explanation: str
    
    passed: int = 0