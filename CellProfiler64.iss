; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!
; 
; CellProfiler is distributed under the GNU General Public License.
; See the accompanying file LICENSE for details.
; 
; Copyright (c) 2003-2009 Massachusetts Institute of Technology
; Copyright (c) 2009-2014 Broad Institute
; All rights reserved.
; 
; Please see the AUTHORS file for credits.
; 
; Website: http://www.cellprofiler.org

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{E6064576-236D-4C12-ACBD-BC8B606F9329}
AppName=CellProfiler
#include "version.iss"
AppPublisher=Broad Institute
AppPublisherURL=http://www.cellprofiler.org
AppSupportURL=http://www.cellprofiler.org
AppUpdatesURL=http://www.cellprofiler.org
DefaultDirName={pf64}\CellProfiler
DefaultGroupName=CellProfiler
OutputDir=.\output
SetupIconFile=.\CellProfilerIcon.ico
Compression=lzma
SolidCompression=yes
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
Name: "{userappdata}\CellProfiler\plugins"; Flags: uninsneveruninstall
Name: "{userappdata}\CellProfiler\ijplugins"; Flags: uninsneveruninstall

[Files]
Source: ".\dist\CellProfiler.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".\dist\analysis_worker.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".\dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".\windows\vcredist_x64.exe"; DestDir: "{tmp}"
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\CellProfiler"; Filename: "{app}\CellProfiler.exe"; WorkingDir: "{app}"
#include "ilastik.iss"
Name: "{group}\{cm:ProgramOnTheWeb,CellProfiler}"; Filename: "http://www.cellprofiler.org"
Name: "{group}\{cm:UninstallProgram,CellProfiler}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\CellProfiler"; Filename: "{app}\CellProfiler.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; CellProfiler project file association
Root: HKCR; Subkey: ".cpproj"; ValueType: string; ValueName: ""; ValueData: "CellProfilerProject"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "CellProfilerProject"; ValueType: string; ValueName: ""; ValueData: "CellProfiler project file"; Flags: uninsdeletekey
Root: HKCR; Subkey: "CellProfilerProject\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\CellProfiler.exe,0"
Root: HKCR; Subkey: "CellProfilerProject\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\CellProfiler.exe"" --project ""%1"""
; CellProfiler pipeline file association
Root: HKCR; Subkey: ".cppipe"; ValueType: string; ValueName: ""; ValueData: "CellProfilerPipeline"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "CellProfilerPipeline"; ValueType: string; ValueName: ""; ValueData: "CellProfiler pipeline"; Flags: uninsdeletekey
Root: HKCR; Subkey: "CellProfilerPipeline\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\CellProfiler.exe,0"
Root: HKCR; Subkey: "CellProfilerPipeline\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\CellProfiler.exe"" --pipeline ""%1"""
; default plugins directories
Root: HKCU; Subkey: "Software\CellProfilerLocal.cfg"; ValueType: string; ValueName: "PluginDirectory"; ValueData: {code:EscapeString|%7Buserappdata%7D\CellProfiler\plugins}; Flags: createvalueifdoesntexist
Root: HKCU; Subkey: "Software\CellProfilerLocal.cfg"; ValueType: string; ValueName: "IJPluginDirectory"; ValueData: {code:EscapeString|%7Buserappdata%7D\CellProfiler\ijplugins}; Flags: createvalueifdoesntexist
; Turn on the startup blurb again
Root: HKCU; Subkey: "Software\CellProfilerLocal.cfg"; ValueType: dword; ValueName: "StartupBlurb"; ValueData: "1"
[Run]
Filename: "{tmp}\vcredist_x64.exe"; Parameters: "/q"
Filename: "{app}\CellProfiler.exe"; Description: "{cm:LaunchProgram,CellProfiler}"; Flags: nowait postinstall skipifsilent

[Code]
function EscapeString(Input: String): String;
Var
  Path: String;
Begin
  Path := ExpandConstant(Input);
  StringChangeEx(Path, '\', '\\', True);
  Result := Path;
End;

function IJPluginsRegistryValue(): String;
Begin
  Result := EscapeString('{userappdata}\CellProfiler\ijplugins');
End;

function PluginsRegistryValue(): String;
Begin
  Result := EscapeString('{userappdata}\CellProfiler\plugins');
End;

function InitializeSetup(): Boolean;
Var
  Message: String;
Begin
Message := 'This build can only run on a 64-bit operating system, but yours is 32-bit. '+
           'Please download the Windows 32-bit version of CellProfiler from the '+
           'downloads page at cellprofiler.org.';
  if IsWin64 then Begin
    if (GetWindowsVersion < $06000000) then Begin
      Message := 'Windows XP 64-bit operation is not supported in this release. CellProfiler 2.0 '+
               'is compatible with Windows XP and is available at '+
               'http://cellprofiler.org/previousReleases.shtml';
      MsgBox(Message, mbInformation, MB_OK);
      Result := False;
      End
    else
      Result := True;
    End
  else Begin
    MsgBox(Message, mbInformation, MB_OK);
    Result := False;
  End;
End;
