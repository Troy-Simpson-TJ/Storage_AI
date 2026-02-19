"""
main.py
- This is the entry point (the "face") of the program.
- It simply creates the UI app and starts Tkinter's event loop.
"""

from ui_app import StorageScannerApp


def main():
    # Create the Tkinter application window
    app = StorageScannerApp()
    # Start Tkinter's main loop
    # (This keeps the window open and handles button clicks, redraws, etc.)
    app.mainloop()
    



# This check ensures main() only runs when YOU run `python main.py`
# and not when the file is imported by other modules.
if __name__ == "__main__":
    main()
