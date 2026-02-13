@echo off
echo ========================================================
echo Git Push Helper for Statement Analyzer
echo ========================================================
echo Please create a new EMPTY repository on GitHub first (click the green New button).
echo.
set /p repo_url="Paste your new GitHub Repository URL (e.g. https://github.com/YourName/New-Statement-Analyzer.git): "
echo.
echo Setting remote to: %repo_url%
git remote set-url origin %repo_url%
if errorlevel 1 (
    echo Failed to set remote. Trying to add new remote...
    git remote add origin %repo_url%
)

echo.
echo Pushing code to GitHub...
git push -u origin main

if errorlevel 1 (
    echo.
    echo Push failed. Please check your URL and internet connection.
) else (
    echo.
    echo Successfully pushed! You should see your code on GitHub now.
)
pause
