@ECHO OFF
SET DIRWORK=%~dp0

IF EXIST "%PYTHON%" (
	rem ok
) ELSE (
	set PYTHON=python
)

SET PATH=%~dp0\bin;%PATH%

:: needed for netlib-clapack-prebuilt
:: SET PATH=%~dp0\bin\cmake-3.4.0-win32-x86\bin;%PATH%

"%PYTHON%" %DIRWORK%\build.py %*
exit /b %ERRORLEVEL%

