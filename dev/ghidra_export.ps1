# Import an ELF into a Ghidra project, analyze it, and export decompiled C.
# Usage: ghidra_export.ps1 <elf path> <project name> <output dir> [r2] [r13]
param(
	[Parameter(Mandatory)] [string] $Elf,
	[Parameter(Mandatory)] [string] $Name,
	[Parameter(Mandatory)] [string] $OutDir,
	[string] $R2 = '0x802DF480',
	[string] $R13 = '0x802DFA60'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path (Split-Path -Parent $root) 'tools'
$env:JAVA_HOME = Join-Path $tools 'jdk-21.0.12.1+1'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
$headless = Join-Path $tools 'ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat'
$proj = Join-Path $root 'ghidra_proj'
New-Item -ItemType Directory -Force $proj, $OutDir | Out-Null

& $headless $proj $Name -import $Elf -overwrite `
	-processor 'PowerPC:BE:32:default' -cspec default `
	-scriptPath (Join-Path $PSScriptRoot 'ghidra_scripts') `
	-preScript SetSda.java $R2 $R13 `
	-postScript ExportDecomp.java $OutDir `
	-max-cpu 8
