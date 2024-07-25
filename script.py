# -*- coding: utf-8 -*-
import clr 
import os
import sys

clr.AddReference("System")
from System import Windows
import System

clr.AddReference("RevitServices")
import RevitServices
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
import Autodesk
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')

from Autodesk.Revit.UI import *
from Autodesk.Revit.DB import *
from System.Collections.Generic import *
from Autodesk.Revit.UI.Selection import *


clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference("System.Windows.Forms")

from System.Windows import MessageBox
from System.IO import FileStream, FileMode, FileAccess
from System.Windows.Markup import XamlReader

# Get the directory path of the .py file
dir_path = os.path.dirname(os.path.realpath(__file__))
xaml_file_path = os.path.join(dir_path, "Window.xaml")

#Get UIdoc
uidoc = __revit__.ActiveUIDocument
uiapp = UIApplication(uidoc.Document.Application)
app = uiapp.Application
doc = uidoc.Document
activeView = doc.ActiveView
version = int(app.VersionNumber)
all_floor_types = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Floors).WhereElementIsElementType().ToElements()

#ISelectionFilter for Door
class FilterDoor(ISelectionFilter):
    def AllowElement(self, element):
        if element.Category.Name == "Doors":
             return True
        else:
             return False
       
    def AllowReference(self, reference, position):
        return True

class Utils:
    def __init__(self):
        pass

    #get all floor types in document
    def get_floor_type_names (self):
        all_typy_names = []
        for type in all_floor_types:
            symbol_name = type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            all_typy_names.append(symbol_name)
        all_typy_names.sort()
        return all_typy_names
    
    #get all floor types by name
    def get_floorType_byName (self, floor_type_Name):
        floor_type = None
        for type in all_floor_types:
            symbol_name = type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            if symbol_name == floor_type_Name:
                floor_type = type
                break
        return floor_type
    

    #create floor method
    def create_separate_floor (self, door, floor_type_name, door_height_offset):

        #get door information
        door_type = doc.GetElement(door.GetTypeId())
        door_location = door.Location
        door_point = door_location.Point
        door_angle = door_location.Rotation
        door_width = door_type.get_Parameter(BuiltInParameter.DOOR_WIDTH).AsDouble()

        #get host wall and properties
        wall = door.Host
        wall_type = doc.GetElement(wall.GetTypeId())
        wall_width = wall_type.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM).AsDouble()

        #create curve loops
        p1 = door_point
        p2 = XYZ(p1.X + door_width,p1.Y,p1.Z)
        p3 = XYZ(p2.X,p2.Y + wall_width,p1.Z)
        p4 = XYZ(p1.X,p1.Y + wall_width,p1.Z)
        center = (p1 + p2 + p3 + p4) / 4

        profiles = []
        line1 = Line.CreateBound(p1,p2)
        line2 = Line.CreateBound(p2,p3)
        line3 = Line.CreateBound(p3,p4)
        line4 = Line.CreateBound(p4,p1)
        curveloop = CurveLoop.Create([line1,line2,line3,line4])
        profiles.append(curveloop)

        #get walltypeId and levelId
        level_id = door.LevelId
        floor_type = self.get_floorType_byName(floor_type_name)

        #create floor
        floor = None
        if version > 2021:
                floor = Floor.Create(doc, profiles, floor_type.Id, level_id)
        else:
            curve_array = CurveArray()
            curve_array.Append(line1)
            curve_array.Append(line2)
            curve_array.Append(line3)
            curve_array.Append(line4)
            
            level = doc.GetElement(level_id)
            floor = doc.Create.NewFloor(curve_array, floor_type, level, False)

        if floor is not None:
            Autodesk.Revit.DB.ElementTransformUtils.MoveElement(doc,floor.Id, p1 - center)
            axis = Line.CreateBound(p1, p1 + XYZ.BasisZ)
            Autodesk.Revit.DB.ElementTransformUtils.RotateElement(doc,floor.Id, axis, door_angle)
            floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM).Set(door_height_offset/304.8)

        return floor
    
    #combine floor method
    def combine_floors (self, list_floor, door_height_offset):

        floor_type_id = list_floor[0].GetTypeId()
        level_id = list_floor[0].LevelId    
        profiles = []

        #get new CurrveLoop, delete separate floor
        for floor in list_floor:
            list_line = []
            sketch = doc.GetElement(floor.SketchId)
            curveArrArray = sketch.Profile
            for line in curveArrArray.get_Item(0):
                list_line.append(line)
            curveloop = CurveLoop.Create(list_line)
            profiles.append(curveloop)
            doc.Delete(floor.Id)
        
        #create new floor
        combine_floor = Floor.Create(doc, profiles, floor_type_id, level_id)
        combine_floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM).Set(door_height_offset/304.8)


class WPFWindow:
    def load_window (self, list_doors, floor_type_names):

        #import window from .xaml file path
        file_stream = FileStream(xaml_file_path, FileMode.Open, FileAccess.Read)
        window = XamlReader.Load(file_stream)

        #controls
        self.cbb_family = window.FindName("cbb_Family")
        self.tb_offset = window.FindName("tb_Offset")
        self.cb_combine = window.FindName("cb_Combine")
        self.bt_Cancel = window.FindName("bt_Cancel")
        self.bt_Ok = window.FindName("bt_OK")

        #get/set values
        self.floor_type_names = floor_type_names
        self.list_doors = list_doors

        #bindingdata
        self.bindind_data()
        self.window = window

        return window

    def bindind_data (self):
        self.cbb_family.ItemsSource = self.floor_type_names
        self.bt_Cancel.Click += self.Cancel_Click
        self.bt_Ok.Click += self.OK_Click


    def OK_Click(self, sender, e):

        height_ofsset = float(self.tb_offset.Text)
        floor_type_name = self.cbb_family.SelectedItem
        checked = self.cb_combine.IsChecked

        t = Transaction(doc, "Create floors")
        t.Start()

        #create separate floor
        list_floors = []
        for door in self.list_doors:
            floor =  Utils().create_separate_floor(door, floor_type_name, height_ofsset)
            if floor != None:
                list_floors.append(floor)

        #combine all floor
        if checked == True and version > 2021:
            try:
                Utils().combine_floors(list_floors, height_ofsset)
            except:
                pass
            
        t.Commit()

        MessageBox.Show("Completed!", "Message")


    def Cancel_Click (self, sender, e):
        self.window.Close()

#region Main
class Main ():

    def __init__(self):
        pass

    def get_list_Door (self):
        try:
            list_doors = []
            select_doors = uidoc.Selection.PickElementsByRectangle(FilterDoor(), "Select Doors")
            for door in select_doors:
                wall = door.Host
                wall_type = doc.GetElement(wall.GetTypeId())
                wall_kind = str(wall_type.Kind)
                if wall_kind == "Basic" or wall_kind == "Stacked" or wall_kind == "Unknown":
                    list_doors.append(door)
        except:
            pass
        
        return list_doors

    def main_task(self):
        list_doors = self.get_list_Door()
        if len(list_doors) > 0 :
            floor_type_names = Utils().get_floor_type_names()
            window = WPFWindow().load_window(list_doors, floor_type_names)
            window.ShowDialog()

if __name__ == "__main__":
    Main().main_task()
#endregion
        

                
    
    






