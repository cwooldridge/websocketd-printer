Inno Setup
==========

This repository allows you to create a python executable to connect a printer to a web application.
Para esto se utiliza WinPython e Inno Setup.
* **WinPython**, is a free scientific Python distribution for Windows that is portable.
* **Inno Setup**, is a free software for creating Windows installers.

Download Inno Setup and WinPython
--------------------------------
* Download Inno Setup:
    * https://jrsoftware.org/isinfo.php
* Download python portable:
    *  https://winpython.github.io/

File Structure
--------------
The file structure is defined as :

                 innosetup/
                         WPy32-3771/ #WinPython Folder
                         copying
                         favicon.ico
                         readme.txt
                         requirements.txt
                         websocketd-printer.py


Install Requirements
--------------------
To install python dependencies, it must be positioned in the innosetup folder:

```
# WPy32-3771\scripts\python.bat -m pip install -r requirements.txt
```

Edit websocketd-innosetup.iss
-----------------------------
The **websocketd-innosetup.iss** file allows modifying the creation of the python executable. Before starting to use the variable "MyAppDirectory" must be defined. This indicates the path where the folder with the files to be used will be stored. For this there are 2 options. The first is to change %USER% for our windows user where it is indicated that the folder is on the desktop and the second is to change the entire directory for a new one.

```
	#define MyAppDirectory "C:\Users\%USER%\Desktop\websocketd-printer"
```
```
    Opción 1
	#define MyAppDirectory "C:\Users\EXAMPLE\Desktop\websocketd-printer"
	Opción 2
	#define MyAppDirectory "C:\websocketd-printer"
```
