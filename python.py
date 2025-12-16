import os
import json
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import csv
import threading
import queue
import pandas as pd
import openpyxl
from tkinter import simpledialog
import numpy as np

# ==================== PERFORMANCE OPTIMIZATIONS ====================
# C++-like optimizations for better performance
class FastCache:
    """Memory cache for frequently accessed data"""
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.access_count = {}
    
    def get(self, key):
        """Get cached item with O(1) complexity"""
        if key in self.cache:
            self.access_count[key] = self.access_count.get(key, 0) + 1
            return self.cache[key]
        return None
    
    def set(self, key, value):
        """Set cached item with LRU eviction"""
        if len(self.cache) >= self.max_size:
            # Remove least recently used item
            lru_key = min(self.access_count, key=self.access_count.get)
            del self.cache[lru_key]
            del self.access_count[lru_key]
        self.cache[key] = value
        self.access_count[key] = 1
    
    def clear(self):
        """Clear all cache"""
        self.cache.clear()
        self.access_count.clear()

class FastBookLookup:
    """Optimized book lookup with hash tables"""
    def __init__(self):
        self.by_id = {}
        self.by_isbn = {}
        self.by_sno = {}
        self.by_title = {}
        self.title_lower_map = {}
    
    def build_index(self, books):
        """Build multiple hash indexes for O(1) lookups"""
        self.by_id.clear()
        self.by_isbn.clear()
        self.by_sno.clear()
        self.by_title.clear()
        self.title_lower_map.clear()
        
        for book in books:
            book_id = book.get('id')
            if book_id:
                self.by_id[book_id] = book
            
            isbn = book.get('isbn')
            if isbn:
                self.by_isbn[isbn] = book
            
            sno = book.get('s.no_code')
            if sno:
                self.by_sno[sno] = book
            
            title = book.get('title')
            if title:
                self.by_title[title] = book
                self.title_lower_map[title.lower()] = book
    
    def get_by_id(self, book_id):
        """O(1) lookup by ID"""
        return self.by_id.get(book_id)
    
    def get_by_isbn(self, isbn):
        """O(1) lookup by ISBN"""
        return self.by_isbn.get(isbn)
    
    def get_by_sno(self, sno):
        """O(1) lookup by S.no"""
        return self.by_sno.get(sno)
    
    def get_by_title(self, title):
        """O(1) lookup by title (case-insensitive)"""
        return self.title_lower_map.get(title.lower())
    
    def search_by_text(self, search_text):
        """Fast search with prefix matching"""
        search_text = search_text.lower()
        results = []
        
        # Check title matches first (most common search)
        for title_lower, book in self.title_lower_map.items():
            if search_text in title_lower:
                results.append(book)
        
        # Also check author if not enough results
        if len(results) < 10:
            for book in self.by_id.values():
                if search_text in book.get('author', '').lower():
                    if book not in results:
                        results.append(book)
        
        return results[:20]  # Limit results for performance

# ==================== LOADING SPINNER ====================
class LoadingSpinner:
    """A loading spinner overlay for database operations"""
    
    def __init__(self, parent):
        self.parent = parent
        self.window = None
        self.running = False
        self.thread = None
        
    def show(self, message="Saving..."):
        """Show the loading spinner"""
        if self.window and self.window.winfo_exists():
            self.window.destroy()
            
        self.window = tk.Toplevel(self.parent)
        self.window.title("Please Wait")
        self.window.geometry("300x150")
        self.window.configure(bg='white')
        self.window.transient(self.parent)
        self.window.grab_set()
        
        # Center the window
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.window.winfo_screenheight() // 2) - (height // 2)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        
        # Remove window decorations
        self.window.overrideredirect(True)
        
        # Create content
        frame = tk.Frame(self.window, bg='white', relief='solid', bd=1)
        frame.pack(fill='both', expand=True, padx=1, pady=1)
        
        # Spinner frame
        spinner_frame = tk.Frame(frame, bg='white')
        spinner_frame.pack(pady=20)
        
        # Spinner canvas
        self.canvas = tk.Canvas(spinner_frame, width=40, height=40, bg='white', highlightthickness=0)
        self.canvas.pack()
        
        # Create spinner circle
        self.circle = self.canvas.create_arc(5, 5, 35, 35, start=0, extent=90, 
                                            outline='#3498db', width=3, style='arc')
        
        # Message
        tk.Label(frame, text=message, font=('Arial', 12), 
                bg='white', fg='#2c3e50').pack(pady=10)
        
        tk.Label(frame, text="Please wait while saving to database...", 
                font=('Arial', 10), bg='white', fg='#7f8c8d').pack()
        
        self.running = True
        self.animate_spinner()
        
    def animate_spinner(self):
        """Animate the spinner"""
        if not self.running or not self.window or not self.window.winfo_exists():
            return
            
        for i in range(0, 360, 15):
            if not self.running:
                break
            self.canvas.delete(self.circle)
            self.circle = self.canvas.create_arc(5, 5, 35, 35, start=i, extent=90, 
                                                outline='#3498db', width=3, style='arc')
            self.window.update()
            time.sleep(0.05)
            
        if self.running:
            self.window.after(50, self.animate_spinner)
            
    def hide(self):
        """Hide the loading spinner"""
        self.running = False
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None

# ==================== DATA OBSERVER PATTERN ====================
class DataChangeObserver:
    """Observer pattern to notify when data changes"""
    
    def __init__(self):
        self._observers = []
    
    def register_observer(self, observer):
        """Register an observer to be notified of data changes"""
        if observer not in self._observers:
            self._observers.append(observer)
    
    def unregister_observer(self, observer):
        """Unregister an observer"""
        if observer in self._observers:
            self._observers.remove(observer)
    
    def notify_observers(self, change_type, data_id, data=None):
        """Notify all observers of a data change"""
        for observer in self._observers:
            observer.on_data_changed(change_type, data_id, data)

class DataObservable:
    """Base class for observable data objects"""
    
    def __init__(self):
        self.observer = DataChangeObserver()
    
    def add_observer(self, observer):
        """Add an observer to this observable"""
        self.observer.register_observer(observer)
    
    def remove_observer(self, observer):
        """Remove an observer from this observable"""
        self.observer.unregister_observer(observer)
    
    def notify_data_change(self, change_type, data_id, data=None):
        """Notify all observers of a data change"""
        self.observer.notify_observers(change_type, data_id, data)

class BookDataObservable(DataObservable):
    """Observable book data with synchronized updates"""
    
    def __init__(self, data):
        super().__init__()
        self.data = data
    
    def update_book_stock(self, book_id, new_stock_data):
        """Update book stock and notify all observers"""
        # Find and update the book in the main list
        for i, book in enumerate(self.data.books):
            if book['id'] == book_id:
                # Store old values for comparison
                old_stock = book['available_copies']
                old_total = book['total_copies']
                
                # Update the book
                book['available_copies'] = new_stock_data['available_copies']
                book['total_copies'] = new_stock_data['total_copies']
                
                # Notify observers of the change
                self.notify_data_change('BOOK_STOCK_UPDATED', book_id, {
                    'old_stock': old_stock,
                    'new_stock': book['available_copies'],
                    'old_total': old_total,
                    'new_total': book['total_copies'],
                    'book_title': book['title'],
                    'book_author': book['author']
                })
                
                # Save the data
                self.data.save_data()
                return True
        
        return False

class UIUpdater:
    """Observer that updates UI components when data changes"""
    
    def __init__(self, app_instance):
        self.app = app_instance
    
    def on_data_changed(self, change_type, data_id, data=None):
        """Handle data change notifications"""
        if change_type == 'BOOK_STOCK_UPDATED':
            self.update_book_related_ui(data_id, data)
    
    def update_book_related_ui(self, book_id, book_data):
        """Update all UI components showing book data"""
        try:
            # Refresh the admin screen if it's active
            if hasattr(self.app, 'create_admin_screen'):
                # Get current screen
                for widget in self.app.root.winfo_children():
                    if isinstance(widget, tk.Canvas):
                        # Check if we're in admin or stock management screen
                        child_texts = []
                        for child in widget.winfo_children():
                            if isinstance(child, tk.Label):
                                child_texts.append(child.cget('text'))
                        
                        # If we're in stock management, refresh it
                        if any('Manage Stock' in str(t) for t in child_texts):
                            self.app.manage_stock()
                            print(f"✅ Refreshed stock management screen for book {book_id}")
                            return
                        # If we're in admin screen, refresh it
                        elif any('Admin Panel' in str(t) for t in child_texts):
                            self.app.create_admin_screen()
                            print(f"✅ Refreshed admin screen for book {book_id}")
                            return
        except Exception as e:
            print(f"❌ Error updating UI: {e}")

# ==================== STOCK MANAGEMENT SYSTEM ====================
class StockManagementSystem:
    """Handle stock management with out-of-stock, low stock, and restocking features"""
    
    def __init__(self, data):
        self.data = data
        self.stock_history_file = "data/stock_history.json"
        self.load_stock_history()
    
    def load_stock_history(self):
        """Load stock history from file"""
        try:
            with open(self.stock_history_file, 'r') as f:
                self.stock_history = json.load(f)
            print(f"✅ Loaded {len(self.stock_history)} stock history records")
        except:
            self.stock_history = []
    
    def save_stock_history(self):
        """Save stock history to file"""
        os.makedirs('data', exist_ok=True)
        with open(self.stock_history_file, 'w') as f:
            json.dump(self.stock_history, f, indent=4)
    
    def get_out_of_stock_books(self):
        """Get all books with 0 available copies"""
        out_of_stock = []
        for book in self.data.books:
            if book['available_copies'] <= 0:
                out_of_stock.append(book)
        return out_of_stock
    
    def get_low_stock_books(self):
        """Get books with 3 or fewer copies (but not 0)"""
        low_stock = []
        for book in self.data.books:
            if 0 < book['available_copies'] <= 3:
                low_stock.append(book)
        return low_stock
    
    def get_in_stock_books(self):
        """Get books with normal stock"""
        in_stock = []
        for book in self.data.books:
            if book['available_copies'] > 3:
                in_stock.append(book)
        return in_stock
    
    def restock_book(self, book_id, quantity, source="Purchase", notes=""):
        """Restock a single book"""
        for book in self.data.books:
            if book['id'] == book_id:
                # Store old stock for history
                old_stock = book['available_copies']
                old_total = book['total_copies']
                
                # Update stock
                book['available_copies'] += quantity
                book['total_copies'] += quantity
                
                # Add to stock history
                history_record = {
                    "history_id": len(self.stock_history) + 1,
                    "book_id": book_id,
                    "book_title": book['title'],
                    "book_author": book['author'],
                    "book_isbn": book['isbn'],
                    "action": "restock",
                    "quantity_added": quantity,
                    "old_stock": old_stock,
                    "new_stock": book['available_copies'],
                    "old_total": old_total,
                    "new_total": book['total_copies'],
                    "source": source,
                    "notes": notes,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "performed_by": "admin"
                }
                
                self.stock_history.append(history_record)
                self.save_stock_history()
                self.data.save_data()
                
                print(f"✅ Restocked {quantity} copies of '{book['title']}'")
                print(f"   Old stock: {old_stock}, New stock: {book['available_copies']}")
                print(f"   Old total: {old_total}, New total: {book['total_copies']}")
                
                return True, book
        
        return False, None
    
    def bulk_restock_from_excel(self, excel_file_path):
        """Bulk restock from Excel file"""
        try:
            # Read Excel file
            df = pd.read_excel(excel_file_path)
            
            # Check required columns
            required_columns = ['ISBN', 'Quantity']
            for col in required_columns:
                if col not in df.columns:
                    messagebox.showerror("Excel Error", 
                                       f"Excel file must contain '{col}' column")
                    return False
            
            restocked_books = []
            skipped_books = []
            
            for index, row in df.iterrows():
                isbn = str(row['ISBN']).strip()
                quantity = int(row['Quantity'])
                
                # Find book by ISBN
                book_found = False
                for book in self.data.books:
                    if book['isbn'] == isbn:
                        # Restock book
                        old_stock = book['available_copies']
                        old_total = book['total_copies']
                        book['available_copies'] += quantity
                        book['total_copies'] += quantity
                        
                        # Add to history
                        history_record = {
                            "history_id": len(self.stock_history) + 1,
                            "book_id": book['id'],
                            "book_title": book['title'],
                            "book_author": book['author'],
                            "book_isbn": book['isbn'],
                            "action": "bulk_restock",
                            "quantity_added": quantity,
                            "old_stock": old_stock,
                            "new_stock": book['available_copies'],
                            "old_total": old_total,
                            "new_total": book['total_copies'],
                            "source": "Excel Import",
                            "notes": f"Bulk restock from Excel file",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "performed_by": "admin"
                        }
                        
                        self.stock_history.append(history_record)
                        restocked_books.append(book['title'])
                        book_found = True
                        break
                
                if not book_found:
                    skipped_books.append(isbn)
            
            # Save data
            self.save_stock_history()
            self.data.save_data()
            
            # Show summary
            summary = f"✅ Bulk Restock Complete!\n\n"
            summary += f"📚 Books Restocked: {len(restocked_books)}\n"
            if restocked_books:
                summary += f"• {', '.join(restocked_books[:5])}"
                if len(restocked_books) > 5:
                    summary += f"\n• ... and {len(restocked_books)-5} more"
            
            if skipped_books:
                summary += f"\n\n⚠️ Skipped (ISBN not found): {len(skipped_books)}\n"
                summary += f"• {', '.join(skipped_books[:5])}"
                if len(skipped_books) > 5:
                    summary += f"\n• ... and {len(skipped_books)-5} more"
            
            messagebox.showinfo("Bulk Restock Summary", summary)
            return True
            
        except Exception as e:
            messagebox.showerror("Excel Import Error", 
                               f"Failed to import from Excel:\n\n{str(e)}")
            return False
    
    def get_stock_history(self):
        """Get complete stock history"""
        return self.stock_history
    
    def get_book_stock_status(self, book_id):
        """Get stock status of a specific book"""
        for book in self.data.books:
            if book['id'] == book_id:
                if book['available_copies'] <= 0:
                    return "⚠️ OUT OF STOCK"
                elif book['available_copies'] <= 3:
                    return "🔶 LOW STOCK"
                else:
                    return "✅ IN STOCK"
        return "❓ NOT FOUND"

# ==================== GLASS PANEL CLASS ====================
class GlassPanel(tk.Canvas):
    """
    Custom Tkinter Canvas widget that creates a glassmorphism effect
    """
    def __init__(self, parent, width, height, bg_image_path=None, radius=30):
        super().__init__(parent, borderwidth=0, highlightthickness=0, width=width, height=height)
        self.place(relx=0.5, rely=0.5, anchor='center')
        
        self.parent = parent
        self.width = width
        self.height = height
        
        # 1. Process background (the "frosted" effect)
        try:
            if bg_image_path and os.path.exists(bg_image_path):
                # Get the actual background image dimensions from the root window
                root_w, root_h = 1300, 800  # Default size
                
                # Try to get actual window size
                if parent.winfo_exists():
                    root_w = parent.winfo_width()
                    root_h = parent.winfo_height()
                    if root_w < 100 or root_h < 100:
                        root_w, root_h = 1300, 800
                
                # Open main background image and resize to match root geometry
                full_bg = Image.open(bg_image_path)
                full_bg = full_bg.resize((root_w, root_h), Image.Resampling.LANCZOS)
                
                # Calculate centered crop area
                x_center = (root_w - width) // 2
                y_center = (root_h - height) // 2
                
                # Ensure crop coordinates are within bounds
                x_center = max(0, min(x_center, root_w - width))
                y_center = max(0, min(y_center, root_h - height))
                
                crop_box = (x_center, y_center, x_center + width, y_center + height)
                panel_bg = full_bg.crop(crop_box)
                
                # Apply Gaussian blur (frosted effect)
                panel_bg = panel_bg.filter(ImageFilter.GaussianBlur(radius=5))
            else:
                # Fallback to solid color if image missing
                panel_bg = Image.new('RGBA', (width, height), (44, 62, 80, 255))
        except Exception as e:
            print(f"Glass Effect Error: {e}")
            panel_bg = Image.new('RGBA', (width, height), (44, 62, 80, 255))

        # 2. Create glass overlay (semi-transparent white)
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Create rounded rectangle:
        fill_color = (255, 255, 255, 40)
        outline_color = (255, 255, 255, 120)
        
        draw.rounded_rectangle(
            [(0, 0), (width-1, height-1)], 
            radius=radius, 
            fill=fill_color, 
            outline=outline_color, 
            width=2
        )

        # 3. Composite and display
        panel_bg = panel_bg.convert("RGBA")
        final_image = Image.alpha_composite(panel_bg, overlay)
        
        self.tk_image = ImageTk.PhotoImage(final_image)
        self.create_image(0, 0, image=self.tk_image, anchor='nw')

    def add_text(self, x, y, text, font, color='white', anchor='center', justify='center'):
        return self.create_text(x, y, text=text, font=font, fill=color, anchor=anchor, justify=justify)

# ==================== EXCEL INTEGRATION MANAGER ====================
class ExcelManager:
    """Handle Excel file integration with SQLite3 database"""
    
    def __init__(self, data):
        self.data = data
        self.excel_file = "Department_library_books.xlsx"  # Changed to your file name
        self.sheet_name = "Sheet1"
        
    def export_to_excel(self):
        """Export all books from SQLite3 to Excel file in Excel sheet format"""
        try:
            print("\n🔍 Exporting to Excel...")
            
            # Prepare data in Excel sheet format - EXACTLY like your Excel
            excel_data = []
            for book in self.data.books:
                excel_row = {
                    "S.no": book.get('s.no_code', ''),  # Use s.no_code if exists, otherwise ID
                    "Authour Title": book.get('author', ''),  # Author EXACTLY as in Excel
                    "Book title": book.get('title', ''),  # Book title EXACTLY as in Excel
                    "Publisher": book.get('publisher', ''),
                    "Page count": book.get('page_count', 0),
                    "Price": self.format_price_for_excel(book.get('price', 0)),
                    "No ": str(book.get('available_copies', 1))
                }
                excel_data.append(excel_row)
            
            # Create DataFrame with Excel sheet column names - MATCH YOUR EXACT FORMAT
            books_df = pd.DataFrame(excel_data, columns=["S.no", "Authour Title", "Book title", "Publisher", "Page count", "Price", "No "])
            
            # Save to Excel
            books_df.to_excel(self.excel_file, index=False, sheet_name=self.sheet_name)
            
            print(f"✅ Exported {len(self.data.books)} books to Excel: {self.excel_file}")
            return True
            
        except Exception as e:
            print(f"❌ Error exporting to Excel: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def format_price_for_excel(self, price):
        """Format price like Excel sheet (40NR, 95NR, etc.)"""
        try:
            price = float(price)
            return f"{int(price)}NR"
        except:
            return "0NR"
    
    def debug_excel_structure(self):
        """Debug function to check Excel file structure"""
        try:
            excel_file = "Department_library_books.xlsx"
            print(f"\n🔍 DEBUGGING EXCEL FILE: {excel_file}")
            
            if not os.path.exists(excel_file):
                print("❌ Excel file not found!")
                return
            
            # Read Excel file
            print("\n1. Reading Excel file:")
            df = pd.read_excel(excel_file, header=0)
            print(f"   Shape: {df.shape}")
            print(f"   Columns: {list(df.columns)}")
            print(f"   First 5 rows:")
            print(df.head())
            
            return True
            
        except Exception as e:
            print(f"❌ Debug error: {e}")
            return False
    
    def import_from_excel(self):
        """Import books from Excel file to SQLite3 - EXACT DATA VERSION - FIXED"""
        try:
            print("\n" + "="*60)
            print("IMPORT: Importing from Excel (EXACT DATA VERSION)")
            print("="*60)

            print(f"Excel file: {self.excel_file}")

            if not os.path.exists(self.excel_file):
                print(f"❌ Excel file not found: {self.excel_file}")
                messagebox.showerror("Error", f"Excel file not found: {self.excel_file}")
                return False

            # Read Excel file WITHOUT assuming specific column names
            df = pd.read_excel(self.excel_file, sheet_name=0, header=0)
            
            print(f"\n📊 Excel Data Info:")
            print(f"Total rows: {len(df)}")
            print(f"Columns: {list(df.columns)}")
            
            # Debug: Show actual column names
            print(f"\n🔍 Actual column names in Excel:")
            for idx, col in enumerate(df.columns):
                print(f"  {idx}: '{col}'")
            
            # Clear existing books
            self.data.books.clear()
            
            # 🔥 FIXED: Use actual column names from your Excel file
            imported_count = 0
            
            for index, row in df.iterrows():
                try:
                    # Get data using ACTUAL column names from your Excel
                    # Based on your Excel screenshot, the columns are:
                    # 'S.no', 'Authour Title', 'Book title', 'Publisher', 'Page count', 'Price', 'No '
                    
                    s_no_val = str(row.get('S.no', row.get('S.no', row.get('S.no', '')))).strip()
                    author_val = str(row.get('Authour Title', row.get('Authour', ''))).strip()
                    title_val = str(row.get('Book title', row.get('Book', ''))).strip()
                    publisher_val = str(row.get('Publisher', '')).strip()
                    
                    # Handle page count
                    page_count_val = row.get('Page count', row.get('Page count', 0))
                    if pd.isna(page_count_val):
                        page_count_val = 0
                    
                    # Handle price (keep as in Excel: 40NR, 95NR, etc.)
                    price_val = str(row.get('Price', '0NR')).strip()
                    
                    # Handle copies - note the space in 'No '
                    copies_val = row.get('No ', row.get('No', 1))
                    if pd.isna(copies_val):
                        copies_val = 1
                    
                    # Skip empty rows
                    if not any([author_val, title_val, s_no_val]):
                        continue
                    
                    # 🔥 FIX: Create new S.no sequence (1, 2, 3...)
                    imported_count += 1
                    new_s_no = str(imported_count)
                    
                    # Convert price to number (remove NR, USD, etc.)
                    try:
                        # Remove currency text and convert to float
                        price_num = float(str(price_val).replace('NR', '').replace('INR', '').replace('USD', '').replace('HR', '').replace('MIR', '').strip())
                    except:
                        # Try to extract any number from the price string
                        import re
                        numbers = re.findall(r'\d+', str(price_val))
                        if numbers:
                            price_num = float(numbers[0])
                        else:
                            price_num = 0
                    
                    # Create book dictionary - KEEP ORIGINAL DATA
                    book = {
                        "id": imported_count,
                        "s.no_code": new_s_no,  # New sequence
                        "title": title_val,  # Original title
                        "author": author_val,  # Original author
                        "isbn": f"ISBN{imported_count:04d}",
                        "category": "General",
                        "publisher": publisher_val,
                        "publication_year": "2024",
                        "page_count": int(page_count_val),
                        "price": float(price_num),
                        "total_copies": int(copies_val) if copies_val > 0 else 1,
                        "available_copies": int(copies_val) if copies_val > 0 else 1,
                        "shelf_location": "A1",
                        "description": f"{title_val} by {author_val}",
                        "added_date": datetime.now().strftime("%Y-%m-%d"),
                        "original_s_no": s_no_val  # Keep original for reference
                    }
                    
                    # Show first few imports
                    if imported_count <= 3:
                        print(f"\n📚 Sample Book {imported_count}:")
                        print(f"  S.no: {new_s_no} (was: {s_no_val})")
                        print(f"  Author: '{author_val}'")
                        print(f"  Title: '{title_val}'")
                        print(f"  Publisher: '{publisher_val}'")
                        print(f"  Price: {price_val} -> {price_num}")
                        print(f"  Copies: {copies_val}")
                    
                    self.data.books.append(book)
                    
                except Exception as e:
                    print(f"❌ Error in row {index}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Save to JSON
            self.data.save_data()
            
            print("\n" + "="*60)
            print(f"✅ IMPORT COMPLETE!")
            print(f"   Imported: {imported_count} books")
            print(f"   Total in database: {len(self.data.books)} books")
            print("="*60)
            
            # Show summary
            if imported_count > 0:
                print(f"\n📚 First 5 imported books (with new S.no):")
                for i, book in enumerate(self.data.books[:5]):
                    print(f"  {i+1}. S.no: {book['s.no_code']} | Author: '{book['author'][:30]}...' | Title: '{book['title'][:30]}...'")
            
            return imported_count > 0

        except Exception as e:
            print(f"❌ Error importing from Excel: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Excel Import Error", 
                               f"Failed to import from Excel:\n\n{str(e)}")
            return False
    
    def get_books_for_suggestions(self, search_text=""):
        """Get books for auto-suggestions with availability status"""
        suggestions = []
        
        for book in self.data.books:
            if search_text.lower() in book['title'].lower() or \
               search_text.lower() in book['author'].lower() or \
               search_text.lower() in book['isbn'].lower():
                
                status = "✅ Available" if book['available_copies'] > 0 else "❌ OUT OF STOCK"
                copies_info = f"{book['available_copies']} copies" if book['available_copies'] > 0 else "No copies"
                
                suggestions.append({
                    "title": book['title'],
                    "author": book['author'],
                    "isbn": book['isbn'],
                    "available_copies": book['available_copies'],
                    "status": status,
                    "full_info": f"{book['title']} by {book['author']} ({status} - {copies_info})"
                })
        
        return suggestions

# ==================== SQLite3 DATA STRUCTURES ====================
class LibraryData:
    def __init__(self):
        self.books_file = "data/books.json"
        self.members_file = "data/members.json"
        self.transactions_file = "data/transactions.json"
        self.categories_file = "data/categories.json"
        self.admin_saves_file = "data/admin_transaction_saves.json"
        
        # SQLite3 database file
        self.db_file = "data/library.db"
        
        self.books = []
        self.members = []
        self.transactions = []
        self.categories = []
        self.admin_saves = []
        
        # Initialize performance optimizations
        self.book_cache = FastCache(max_size=500)
        self.book_lookup = FastBookLookup()
        
        # Initialize SQLite3 database
        self.init_sqlite_database()
        self.load_data()
    
    def init_sqlite_database(self):
        """Initialize SQLite3 database with all tables"""
        os.makedirs('data', exist_ok=True)
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Create admin_saves table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_saves (
                save_id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER,
                save_timestamp TEXT,
                transaction_type TEXT,
                student_name TEXT NOT NULL,
                student_phone TEXT,
                member_id TEXT,
                member_name TEXT,
                member_type TEXT,
                book_id INTEGER,
                book_title TEXT NOT NULL,
                book_author TEXT NOT NULL,
                book_isbn TEXT NOT NULL,
                book_category TEXT,
                issue_date TEXT,
                due_date TEXT,
                return_date TEXT,
                status TEXT,
                fine_amount REAL DEFAULT 0,
                fine_paid INTEGER DEFAULT 0,
                renewals INTEGER DEFAULT 0,
                issue_timestamp TEXT
            )
        ''')
        
        # Create books table for better performance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books_sqlite (
                book_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                isbn TEXT UNIQUE,
                category TEXT,
                available INTEGER DEFAULT 1
            )
        ''')
        
        # Create transactions table for better performance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions_sqlite (
                trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER,
                student_name TEXT,
                issue_date TEXT,
                due_date TEXT,
                return_date TEXT,
                status TEXT,
                fine_amount REAL DEFAULT 0
            )
        ''')
        
        # Create index for faster searches
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_saves_status ON admin_saves(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_saves_student ON admin_saves(student_name)')
        
        conn.commit()
        conn.close()
        print("✅ SQLite3 database initialized successfully")
    
    def load_data(self):
        """Load all data from both JSON files and SQLite database"""
        os.makedirs('data', exist_ok=True)
        
        # Load books from JSON
        try:
            with open(self.books_file, 'r') as f:
                self.books = json.load(f)
            print(f"✅ Loaded {len(self.books)} books from JSON")
        except Exception as e:
            print(f"❌ Error loading books from JSON: {e}")
            self.books = []
        
        # Ensure all books have s.no_code for lookup
        for book in self.books:
            if 's.no_code' not in book or not book.get('s.no_code'):
                book['s.no_code'] = str(book.get('id', ''))
        
        # Save updated data if any changes
        if self.books:
            self.save_data()
        
        # Build fast lookup index for books
        self.book_lookup.build_index(self.books)
        
        # Load members from JSON
        try:
            with open(self.members_file, 'r') as f:
                self.members = json.load(f)
            print(f"✅ Loaded {len(self.members)} members from JSON")
        except:
            self.members = []
        
        # Load transactions from JSON
        try:
            with open(self.transactions_file, 'r') as f:
                self.transactions = json.load(f)
            print(f"✅ Loaded {len(self.transactions)} transactions from JSON")
        except:
            self.transactions = []
        
        # Load categories from JSON
        try:
            with open(self.categories_file, 'r') as f:
                self.categories = json.load(f)
            print(f"✅ Loaded {len(self.categories)} categories from JSON")
        except:
            self.categories = ["Fiction", "Non-Fiction", "Science", "History", "Technology", "Arts", "Biography"]
        
        # Load admin saves from SQLite3 database
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM admin_saves ORDER BY save_timestamp DESC")
            self.admin_saves = [dict(row) for row in cursor.fetchall()]
            conn.close()
            print(f"✅ Loaded {len(self.admin_saves)} admin saves from SQLite3 database")
        except Exception as e:
            print(f"❌ Error loading admin saves from SQLite3: {e}")
            try:
                with open(self.admin_saves_file, 'r') as f:
                    self.admin_saves = json.load(f)
                print(f"✅ Loaded {len(self.admin_saves)} admin saves from JSON backup")
            except:
                self.admin_saves = []
    
    def save_data(self):
        """Save all data to both JSON files and SQLite database"""
        os.makedirs('data', exist_ok=True)
        
        # Save books to JSON
        try:
            with open(self.books_file, 'w') as f:
                json.dump(self.books, f, indent=4)
            print(f"✅ Saved {len(self.books)} books to JSON")
        except Exception as e:
            print(f"❌ Error saving books to JSON: {e}")
        
        # Save members to JSON
        try:
            with open(self.members_file, 'w') as f:
                json.dump(self.members, f, indent=4)
            print(f"✅ Saved {len(self.members)} members to JSON")
        except Exception as e:
            print(f"❌ Error saving members to JSON: {e}")
        
        # Save transactions to JSON
        try:
            with open(self.transactions_file, 'w') as f:
                json.dump(self.transactions, f, indent=4)
            print(f"✅ Saved {len(self.transactions)} transactions to JSON")
        except Exception as e:
            print(f"❌ Error saving transactions to JSON: {e}")
        
        # Save categories to JSON
        try:
            with open(self.categories_file, 'w') as f:
                json.dump(self.categories, f, indent=4)
        except:
            pass
        
        # Save admin saves to JSON for backup
        try:
            with open(self.admin_saves_file, 'w') as f:
                json.dump(self.admin_saves, f, indent=4)
            print(f"✅ Saved {len(self.admin_saves)} admin saves to JSON backup")
        except Exception as e:
            print(f"❌ Error saving admin saves to JSON: {e}")
    
    def add_admin_save_sqlite(self, save_data):
        """Add a new admin save record to SQLite3 database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Prepare SQL query
            columns = []
            values = []
            for key, value in save_data.items():
                columns.append(key)
                values.append(value)
            
            placeholders = ', '.join(['?' for _ in columns])
            columns_str = ', '.join(columns)
            
            query = f"INSERT INTO admin_saves ({columns_str}) VALUES ({placeholders})"
            cursor.execute(query, values)
            
            save_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            
            # Also add to in-memory list for compatibility
            save_data_copy = save_data.copy()
            save_data_copy["save_id"] = save_id
            self.admin_saves.append(save_data_copy)
            
            # Cache the save
            cache_key = f"save_{save_id}"
            self.book_cache.set(cache_key, save_data_copy)
            
            print(f"✅ Saved admin save to SQLite3 database with ID: {save_id}")
            return save_id
            
        except Exception as e:
            print(f"❌ Error saving to SQLite3 database: {e}")
            save_id = len(self.admin_saves) + 1
            save_data["save_id"] = save_id
            self.admin_saves.append(save_data)
            self.save_data()
            return save_id
    
    def get_admin_saves_count_sqlite(self):
        """Get count of admin saves from SQLite3 database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admin_saves")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            return len(self.admin_saves)
    
    def get_today_admin_saves_sqlite(self):
        """Get today's admin saves from SQLite3 database"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admin_saves WHERE save_timestamp LIKE ?", (f"{today}%",))
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            today = datetime.now().strftime("%Y-%m-%d")
            return len([save for save in self.admin_saves if save.get("save_timestamp", "").startswith(today)])
    
    def get_active_borrowers_sqlite(self):
        """Get active borrowers data from SQLite3 database"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    student_name,
                    student_phone,
                    --student_email,  -- NEW: Include email - REMOVED
                    --email_sent,    -- NEW: Include email status - REMOVED
                    book_title,
                    book_author,
                    book_isbn,
                    issue_date,
                    due_date,
                    status,
                    save_timestamp,
                    fine_amount,
                    member_type
                FROM admin_saves 
                WHERE status = 'issued'
                ORDER BY save_timestamp DESC
            """)
            
            active_borrowers = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            print(f"✅ Loaded {len(active_borrowers)} active borrowers from SQLite3 database")
            return active_borrowers
            
        except Exception as e:
            print(f"❌ Error loading active borrowers from SQLite3: {e}")
            return []
    
    def get_active_borrowers_count_sqlite(self):
        """Get count of active borrowers from SQLite3 database"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT student_name) FROM admin_saves WHERE status = 'issued'")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except:
            return 0
    
    def get_recent_saves(self, limit=50):
        """Get recent saves for better performance"""
        try:
            cache_key = f"recent_saves_{limit}"
            cached = self.book_cache.get(cache_key)
            if cached:
                return cached
            
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM admin_saves 
                ORDER BY save_timestamp DESC 
                LIMIT ?
            """, (limit,))
            saves = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            # Cache the result
            self.book_cache.set(cache_key, saves)
            return saves
        except:
            return self.admin_saves[:limit]

# ==================== ASYNC DATABASE MANAGER ====================
class AsyncDatabaseManager:
    """Handle database operations in background threads"""
    
    def __init__(self, data):
        self.data = data
        self.queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.running = True
        self.start_worker()
    
    def start_worker(self):
        """Start background worker thread"""
        self.worker_thread = threading.Thread(target=self._database_worker, daemon=True)
        self.worker_thread.start()
    
    def _database_worker(self):
        """Background worker for database operations"""
        while self.running:
            try:
                task = self.queue.get(timeout=1)
                if task[0] == 'save':
                    save_data = task[1]
                    result = self.data.add_admin_save_sqlite(save_data)
                    self.result_queue.put(('save', result))
                elif task[0] == 'load':
                    result = self.data.get_recent_saves(100)
                    self.result_queue.put(('load', result))
                elif task[0] == 'active':
                    result = self.data.get_active_borrowers_sqlite()
                    self.result_queue.put(('active', result))
                elif task[0] == 'stats':
                    count = self.data.get_admin_saves_count_sqlite()
                    today = self.data.get_today_admin_saves_sqlite()
                    active = self.data.get_active_borrowers_count_sqlite()
                    self.result_queue.put(('stats', (count, today, active)))
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Database worker error: {e}")
                self.result_queue.put(('error', str(e)))
    
    def save_async(self, save_data):
        """Save data asynchronously"""
        self.queue.put(('save', save_data))
    
    def load_async(self):
        """Load data asynchronously"""
        self.queue.put(('load', None))
    
    def get_active_async(self):
        """Get active borrowers asynchronously"""
        self.queue.put(('active', None))
    
    def get_stats_async(self):
        """Get statistics asynchronously"""
        self.queue.put(('stats', None))
    
    def stop(self):
        """Stop the worker thread"""
        self.running = False
        self.worker_thread.join(timeout=5)

# ==================== HISTORY MANAGEMENT SYSTEM ====================
class HistoryManager:
    def __init__(self, data):
        self.data = data
        self.history_file = "data/transaction_history.json"
        self.history_cache = FastCache(max_size=200)
        self.load_history()
    
    def load_history(self):
        """Load transaction history from file"""
        try:
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
            print(f"✅ Loaded {len(self.history)} history records")
        except:
            self.history = []
    
    def save_history(self):
        """Save transaction history to file"""
        os.makedirs('data', exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=4)
    
    def add_to_history(self, transaction_id, book_id, member_id, action):
        """Add a transaction to history with real-time timestamp"""
        # Check cache first
        cache_key = f"history_{transaction_id}_{book_id}_{member_id}"
        cached = self.history_cache.get(cache_key)
        if cached:
            return cached
        
        book_manager = BookManager(self.data)
        book = book_manager.get_book_by_id(book_id)
        
        member_manager = MemberManager(self.data)
        member = member_manager.get_member_by_id(member_id)
        
        history_record = {
            "history_id": len(self.history) + 1,
            "transaction_id": transaction_id,
            "action": action,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "book_id": book_id,
            "book_title": book["title"] if book else "Unknown",
            "book_author": book["author"] if book else "Unknown",
            "book_isbn": book["isbn"] if book else "Unknown",
            "member_id": member_id,
            "member_name": member["name"] if member else "Unknown",
            "member_type": member["membership_type"] if member else "Unknown"
        }
        
        self.history.append(history_record)
        self.save_history()
        
        # Cache the result
        self.history_cache.set(cache_key, history_record)
        return history_record
    
    def get_all_history(self):
        """Get complete transaction history"""
        return self.history

# ==================== ADMIN PANEL SAVER (UPDATED FOR EMAILS) ====================
class AdminPanelSaver:
    def __init__(self, data, transaction_manager, history_manager):
        self.data = data
        self.transaction_manager = transaction_manager
        self.history_manager = history_manager
        
    def save_transaction_to_admin(self, transaction_data, student_name, phone, email, book_name, book_author, isbn_code):
        """Save transaction to SQLite3 database with email"""
        try:
            current_time = datetime.now()
            
            member_manager = MemberManager(self.data)
            member_id = transaction_data.get("member_id", "")
            member = member_manager.get_member_by_id(member_id)
            
            book_manager = BookManager(self.data)
            book = book_manager.get_book_by_id(transaction_data.get("book_id", 0))
            
            save_record = {
                "transaction_id": transaction_data.get("id", 0),
                "save_timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "transaction_type": "manual_issue",
                "student_name": student_name,
                "student_phone": phone,
                #"student_email": email,  # NEW: Email field - REMOVED
                #"email_sent": 0,  # NEW: Email status - REMOVED
                "member_id": member_id,
                "member_name": member["name"] if member else student_name,
                "member_type": member["membership_type"] if member else "Student",
                "book_id": transaction_data.get("book_id", 0),
                "book_title": book_name,
                "book_author": book_author,
                "book_isbn": isbn_code,
                "book_category": book["category"] if book else "General",
                "issue_date": transaction_data.get("issue_date", ""),
                "due_date": transaction_data.get("due_date", ""),
                "return_date": transaction_data.get("return_date", ""),
                "status": transaction_data.get("status", "issued"),
                "fine_amount": transaction_data.get("fine_amount", 0),
                "fine_paid": 1 if transaction_data.get("fine_paid", False) else 0,
                "renewals": transaction_data.get("renewals", 0),
                "issue_timestamp": transaction_data.get("issue_timestamp", current_time.strftime("%Y-%m-%d %H:%M:%S"))
            }
            
            save_id = self.data.add_admin_save_sqlite(save_record)
            print(f"✅ Transaction saved to SQLite3 database with ID: {save_id}")
            
            return save_id
            
        except Exception as e:
            print(f"❌ Error saving to admin panel: {e}")
            return None
    
    def get_all_admin_saves(self):
        """Get all admin panel saves"""
        return self.data.admin_saves
    
    def clear_all_saves(self):
        """Clear all admin saves from SQLite3 database"""
        try:
            conn = sqlite3.connect(self.data.db_file)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_saves")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='admin_saves'")
            conn.commit()
            conn.close()
            
            self.data.admin_saves = []
            self.data.book_cache.clear()
            self.data.save_data()
            print("✅ Cleared all admin saves from SQLite3 database")
        except Exception as e:
            print(f"❌ Error clearing SQLite3 database: {e}")
            self.data.admin_saves = []
            self.data.save_data()
            print("✅ Cleared all admin saves from JSON backup")
    
    def export_to_csv(self, filename):
        """Export admin saves to CSV from SQLite3 database"""
        try:
            conn = sqlite3.connect(self.data.db_file)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT save_id, transaction_id, save_timestamp, student_name, 
                       student_phone, --student_email, --email_sent, book_title, 
                       book_author, book_isbn, issue_date, due_date, status, 
                       fine_amount, fine_paid
                FROM admin_saves
                ORDER BY save_timestamp DESC
            """)
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Save ID", "Transaction ID", "Save Timestamp", "Student Name", 
                               "Student Phone", --"Student Email", --"Email Sent", "Book Title", 
                               "Book Author", "ISBN", "Issue Date", "Due Date", "Status", 
                               "Fine Amount", "Fine Paid"])
                
                for row in cursor.fetchall():
                    writer.writerow(row)
            
            conn.close()
            return True
        except Exception as e:
            print(f"❌ SQLite3 export error: {e}")
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Save ID", "Transaction ID", "Save Timestamp", "Student Name", 
                                   "Student Phone", --"Student Email", --"Email Sent", "Book Title", 
                                   "Book Author", "ISBN", "Issue Date", "Due Date", "Status", 
                                   "Fine Amount", "Fine Paid"])
                    
                    for save in self.data.admin_saves:
                        writer.writerow([
                            save.get("save_id", ""),
                            save.get("transaction_id", ""),
                            save.get("save_timestamp", ""),
                            save.get("student_name", ""),
                            save.get("student_phone", ""),
                            #save.get("student_email", ""),
                            #save.get("email_sent", 0),
                            save.get("book_title", ""),
                            save.get("book_author", ""),
                            save.get("book_isbn", ""),
                            save.get("issue_date", ""),
                            save.get("due_date", ""),
                            save.get("status", ""),
                            save.get("fine_amount", 0),
                            save.get("fine_paid", False)
                        ])
                return True
            except Exception as e2:
                print(f"❌ JSON export error: {e2}")
                return False

# ==================== BOOK MANAGEMENT ====================
class BookManager:
    def __init__(self, data):
        self.data = data
    
    def add_book(self, book_data):
        """Add a new book to the catalog"""
        book_id = len(self.data.books) + 1
        book = {
            "id": book_id,
            "s.no_code": book_data.get("s.no_code", f"T{book_id}"),  # Add s.no_code
            "title": book_data["title"],
            "author": book_data["author"],
            "isbn": book_data["isbn"],
            "category": book_data["category"],
            "publisher": book_data["publisher"],
            "publication_year": book_data["publication_year"],
            "page_count": book_data["page_count"],
            "price": book_data["price"],
            "total_copies": book_data["total_copies"],
            "available_copies": book_data["total_copies"],
            "shelf_location": book_data.get("shelf_location", ""),
            "description": book_data.get("description", ""),
            "added_date": datetime.now().strftime("%Y-%m-%d")
        }
        self.data.books.append(book)
        
        # Update the fast lookup index
        self.data.book_lookup.build_index(self.data.books)
        
        self.data.save_data()
        return book_id
    
    def get_book_by_id(self, book_id):
        """Get book details by ID - O(1) with cache"""
        # Check cache first
        cache_key = f"book_{book_id}"
        cached = self.data.book_cache.get(cache_key)
        if cached:
            return cached
        
        # Use fast lookup
        book = self.data.book_lookup.get_by_id(book_id)
        if book:
            self.data.book_cache.set(cache_key, book)
        return book
    
    def get_book_by_sno(self, s_no):
        """Get book details by S.no - O(1) with cache"""
        # Check cache first
        cache_key = f"book_sno_{s_no}"
        cached = self.data.book_cache.get(cache_key)
        if cached:
            return cached
        
        # Use fast lookup
        book = self.data.book_lookup.get_by_sno(s_no)
        if book:
            self.data.book_cache.set(cache_key, book)
        return book
    
    def update_book(self, book_id, updated_data):
        """Update existing book information"""
        for i, book in enumerate(self.data.books):
            if book["id"] == book_id:
                # Store old values for notification
                old_stock = book['available_copies']
                old_total = book['total_copies']
                
                # Update the book data
                for key, value in updated_data.items():
                    if key in book:
                        book[key] = value
                
                # Update available copies if total copies changed
                if "total_copies" in updated_data:
                    old_total = self.data.books[i]["total_copies"]
                    new_total = updated_data["total_copies"]
                    if new_total > old_total:
                        # If increasing total copies, also increase available copies
                        diff = new_total - old_total
                        book["available_copies"] += diff
                    elif new_total < old_total:
                        # If decreasing total copies, adjust available copies
                        # but don't go below 0
                        diff = old_total - new_total
                        book["available_copies"] = max(0, book["available_copies"] - diff)
                        # Ensure total copies matches new total
                        book["total_copies"] = new_total
                
                # Update the fast lookup index
                self.data.book_lookup.build_index(self.data.books)
                
                # Clear relevant cache entries
                self.data.book_cache.clear()
                
                self.data.save_data()
                return True
        return False
    
    def delete_book(self, book_id):
        """Delete a book from the catalog"""
        for i, book in enumerate(self.data.books):
            if book["id"] == book_id:
                # Check if book is currently issued
                if book["available_copies"] < book["total_copies"]:
                    messagebox.showerror("Cannot Delete", 
                                       f"Cannot delete '{book['title']}'. "
                                       f"Book is currently issued ({book['total_copies'] - book['available_copies']} copies).")
                    return False
                
                # Remove the book
                del self.data.books[i]
                
                # Update the fast lookup index
                self.data.book_lookup.build_index(self.data.books)
                
                # Clear cache
                self.data.book_cache.clear()
                
                self.data.save_data()
                return True
        return False
    
    def delete_selected_books(self, book_ids):
        """Delete multiple books at once"""
        books_to_delete = []
        books_with_issues = []
        
        # First, check all books using fast lookup
        for book_id in book_ids:
            book = self.data.book_lookup.get_by_id(book_id)
            if book:
                if book["available_copies"] < book["total_copies"]:
                    books_with_issues.append(book)
                else:
                    books_to_delete.append(book)
        
        if books_with_issues:
            book_list = "\n".join([f"• '{book['title']}' ({book['total_copies'] - book['available_copies']} copies issued)" for book in books_with_issues])
            messagebox.showerror("Cannot Delete", 
                               f"Cannot delete these books:\n{book_list}\n\nThey are currently issued.")
            if not books_to_delete:
                return False
        
        # Delete books that can be deleted
        for book in books_to_delete:
            for i, b in enumerate(self.data.books):
                if b["id"] == book["id"]:
                    del self.data.books[i]
                    break
        
        # Update the fast lookup index
        self.data.book_lookup.build_index(self.data.books)
        
        # Clear cache
        self.data.book_cache.clear()
        
        self.data.save_data()
        
        if books_to_delete:
            deleted_count = len(books_to_delete)
            if books_with_issues:
                messagebox.showinfo("Partial Success", 
                                  f"✅ Deleted {deleted_count} books successfully.\n"
                                  f"⚠️ Could not delete {len(books_with_issues)} books (currently issued).")
            else:
                messagebox.showinfo("Success", f"✅ Deleted {deleted_count} books successfully.")
            return True
        
        return False
    
    def get_statistics(self):
        """Get library statistics with caching"""
        cache_key = "library_stats"
        cached = self.data.book_cache.get(cache_key)
        if cached:
            return cached
        
        total_books = len(self.data.books)
        total_copies = sum(book.get("total_copies", 1) for book in self.data.books)
        available_copies = sum(book.get("available_copies", 0) for book in self.data.books)
        borrowed_copies = total_copies - available_copies
        
        # Fast category counting using dictionary
        categories = {}
        for book in self.data.books:
            cat = book.get("category", "General")
            categories[cat] = categories.get(cat, 0) + 1
        
        admin_saves = self.data.get_admin_saves_count_sqlite()
        today_admin_saves = self.data.get_today_admin_saves_sqlite()
        active_borrowers_count = self.data.get_active_borrowers_count_sqlite()
        
        stats = {
            "total_books": total_books,
            "total_copies": total_copies,
            "available_copies": available_copies,
            "borrowed_copies": borrowed_copies,
            "categories": categories,
            "active_members": len([m for m in self.data.members if m.get('active', True)]),
            "active_borrowings": len([t for t in self.data.transactions if t.get('status') == 'issued']),
            "total_members": len(self.data.members),
            "admin_saves": admin_saves,
            "today_admin_saves": today_admin_saves,
            "active_borrowers_sqlite": active_borrowers_count
        }
        
        # Cache the stats for 5 seconds
        self.data.book_cache.set(cache_key, stats)
        return stats

# ==================== MEMBER MANAGEMENT ====================
class MemberManager:
    def __init__(self, data):
        self.data = data
    
    def add_member(self, member_data):
        """Add a new library member"""
        member_id = f"M{len(self.data.members) + 1:04d}"
        member = {
            "id": member_id,
            "name": member_data["name"],
            "email": member_data["email"],
            "phone": member_data["phone"],
            "address": member_data["address"],
            "membership_type": member_data["membership_type"],
            "membership_date": datetime.now().strftime("%Y-%m-%d"),
            "max_books": member_data["max_books"],
            "active": True,
            "total_borrowed": 0,
            "current_borrowed": 0,
            "join_date": datetime.now().strftime("%Y-%m-%d")
        }
        self.data.members.append(member)
        self.data.save_data()
        return member_id
    
    def get_member_by_id(self, member_id):
        """Get member details by ID - O(n) but small dataset"""
        for member in self.data.members:
            if member["id"] == member_id and member.get("active", True):
                return member
        return None
    
    def update_borrow_count(self, member_id, delta):
        """Update member's borrowed book count"""
        for member in self.data.members:
            if member["id"] == member_id:
                member["current_borrowed"] += delta
                member["total_borrowed"] += abs(delta)
                if member["current_borrowed"] < 0:
                    member["current_borrowed"] = 0
                self.data.save_data()
                return True
        return False

# ==================== TRANSACTION MANAGEMENT ====================
class TransactionManager:
    def __init__(self, data):
        self.data = data
        self.loan_period = 14
        self.daily_fine = 10
    
    def issue_book(self, book_id, member_id):
        """Issue a book to a member"""
        # Use fast lookup for book
        book = self.data.book_lookup.get_by_id(book_id)
        
        if not book or book["available_copies"] <= 0:
            return False, "Book not available"
        
        member_manager = MemberManager(self.data)
        
        transaction_id = len(self.data.transactions) + 1
        issue_date = datetime.now()
        due_date = issue_date + timedelta(days=self.loan_period)
        
        transaction = {
            "id": transaction_id,
            "book_id": book_id,
            "member_id": member_id,
            "issue_date": issue_date.strftime("%Y-%m-%d"),
            "due_date": due_date.strftime("%Y-%m-%d"),
            "return_date": "",
            "status": "issued",
            "fine_amount": 0,
            "fine_paid": False,
            "renewals": 0
        }
        
        book["available_copies"] -= 1
        
        member_manager.update_borrow_count(member_id, 1)
        
        self.data.transactions.append(transaction)
        self.data.save_data()
        
        # Clear book cache since stock changed
        self.data.book_cache.clear()
        
        return True, f"Book issued successfully. Due date: {due_date.strftime('%Y-%m-%d')}"
    
    def calculate_fine(self, due_date_str):
        """Calculate overdue fine - optimized date calculation"""
        try:
            # Pre-calculate today's date once
            today = datetime.now()
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
            
            if today > due_date:
                days_overdue = (today - due_date).days
                return days_overdue * self.daily_fine
            return 0
        except:
            return 0
    
    def get_overdue_transactions(self):
        """Get all overdue transactions"""
        overdue = []
        today = datetime.now()
        
        for transaction in self.data.transactions:
            if transaction["status"] == "issued":
                try:
                    due_date = datetime.strptime(transaction["due_date"], "%Y-%m-%d")
                    if today > due_date:
                        days_overdue = (today - due_date).days
                        fine = days_overdue * self.daily_fine
                        overdue.append({
                            **transaction,
                            "overdue_days": days_overdue,
                            "fine_amount": fine
                        })
                except:
                    continue
        return overdue

# ==================== DEBUG FUNCTION ====================
def debug_sqlite_connection():
    """Debug function to check SQLite3 connection and data"""
    try:
        db_file = "data/library.db"
        print(f"\n=== DEBUG SQLite3 CONNECTION ===")
        print(f"Database file: {db_file}")
        print(f"File exists: {os.path.exists(db_file)}")
        
        if os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"Tables in database: {[table[0] for table in tables]}")
            
            cursor.execute("SELECT COUNT(*) FROM admin_saves")
            count = cursor.fetchone()[0]
            print(f"Rows in admin_saves table: {count}")
            
            if count > 0:
                cursor.execute("SELECT student_name, --student_email, --email_sent FROM admin_saves ORDER BY save_id DESC LIMIT 3")
                recent_rows = cursor.fetchall()
                print(f"Recent data: {recent_rows}")
            
            conn.close()
        else:
            print("❌ Database file does not exist!")
            
        print("=== END DEBUG ===\n")
    except Exception as e:
        print(f"❌ Debug error: {e}")

# ==================== MAIN APPLICATION CLASS ====================
class LibraryManagementSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Library Management System - Glass Edition")
        self.root.geometry("1300x800")
        self.root.configure(bg='#2c3e50')
        
        self.current_bg_path = None
        self.bg_photo = None
        
        self.admin_password = "admin123"
        
        self.data = LibraryData()
        self.book_manager = BookManager(self.data)
        self.member_manager = MemberManager(self.data)
        self.transaction_manager = TransactionManager(self.data)
        
        # Initialize Data Observer System
        self.book_observable = BookDataObservable(self.data)
        self.ui_updater = UIUpdater(self)
        self.book_observable.add_observer(self.ui_updater)
        
        self.history_manager = HistoryManager(self.data)
        
        # Admin Panel Saver
        self.admin_saver = AdminPanelSaver(self.data, self.transaction_manager, 
                                          self.history_manager)
        
        # Async database manager
        self.async_db = AsyncDatabaseManager(self.data)
        
        # Excel Manager
        self.excel_manager = ExcelManager(self.data)
        
        # Stock Management System
        self.stock_manager = StockManagementSystem(self.data)
        
        # Loading Spinner
        self.loading_spinner = LoadingSpinner(self.root)
        
        self.clock_running = False
        
        self.root.update_idletasks()
        self.create_welcome_screen()
        
        debug_sqlite_connection()
        
        # Auto-import from Excel on startup
        self.auto_import_from_excel()
        
        # For multi-selection
        self.selected_books_for_delete = set()
    
    def auto_import_from_excel(self):
        """Auto-import books from Excel on startup"""
        print("\n🔄 Auto-importing books from Excel on startup...")
        excel_file = "Department_library_books.xlsx"
        
        if os.path.exists(excel_file):
            print(f"📁 Found Excel file: {excel_file}")
            
            # Check if we already have books
            if len(self.data.books) == 0:
                print("📚 No books in database. Auto-importing from Excel...")
                success = self.excel_manager.import_from_excel()
                if success:
                    print(f"✅ Auto-imported {len(self.data.books)} books from Excel")
                else:
                    print("❌ Auto-import failed")
            else:
                print(f"✅ Database already has {len(self.data.books)} books. Skipping auto-import.")
        else:
            print(f"⚠️ Excel file '{excel_file}' not found. Skipping auto-import.")
    
    def set_background(self, image_path):
        """Sets a full-screen background image"""
        self.current_bg_path = image_path
        try:
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Label) and hasattr(widget, '_is_bg_label'):
                    widget.destroy()
            
            if not os.path.exists(image_path):
                bg_label = tk.Label(self.root, bg='#2c3e50')
                bg_label._is_bg_label = True
                bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                return

            window_width = self.root.winfo_width()
            window_height = self.root.winfo_height()
            
            if window_width < 10 or window_height < 10:
                window_width, window_height = 1300, 800
            
            img = Image.open(image_path)
            img = img.resize((window_width, window_height), Image.Resampling.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(img)
            
            bg_label = tk.Label(self.root, image=self.bg_photo)
            bg_label._is_bg_label = True
            bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            bg_label.lower()
            
            self.root.bind('<Configure>', self._update_background)
            
        except Exception as e:
            print(f"Error setting background: {e}")
            bg_label = tk.Label(self.root, bg='#2c3e50')
            bg_label._is_bg_label = True
            bg_label.place(x=0, y=0, relwidth=1, relheight=1)

    def _update_background(self, event=None):
        """Update background when window is resized"""
        if self.current_bg_path and hasattr(self, 'bg_photo'):
            try:
                window_width = self.root.winfo_width()
                window_height = self.root.winfo_height()
                
                if window_width > 10 and window_height > 10:
                    img = Image.open(self.current_bg_path)
                    img = img.resize((window_width, window_height), Image.Resampling.LANCZOS)
                    self.bg_photo = ImageTk.PhotoImage(img)
                    
                    for widget in self.root.winfo_children():
                        if isinstance(widget, tk.Label) and hasattr(widget, '_is_bg_label'):
                            widget.config(image=self.bg_photo)
                            widget.image = self.bg_photo
                            break
            except:
                pass

    # ==================== WELCOME SCREEN ====================
    def create_welcome_screen(self):
        """Main welcome screen with Glassmorphism"""
        for widget in self.root.winfo_children():
            widget.destroy()
            
        bg_path = "welcome_bg.jpg" 
        self.set_background(bg_path)
        
        panel_w, panel_h = 1000, 600
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path)
        
        glass.add_text(panel_w//2, 70, "📚 Library Management System", 
                      ('Arial', 28, 'bold'), color='white')
        
        glass.create_line(100, 110, panel_w-100, 110, fill='white', width=2)
        
        instructions_text = (
                   "🎯 LIBRARY FEATURES:\n\n"
            "• Manage books catalog with author, title, ISBN\n"
            "• Track book copies (available vs total)\n"
            "• Issue books to members with due dates\n"
            "• Auto-save to SQLite3 Database (NEW)\n"
            "• Real-time data validation (NEW)\n"
            "• Active Borrowers from SQLite3 (NEW)\n"
            "• Excel Integration (NEW)\n"
            "• Smart Book Suggestions (NEW)\n"
            "• Out-of-Stock Protection (NEW)\n"
            "• � Real-time Data Synchronization\n"
            "• ✏️ Edit/Delete Books (NEW - Select multiple for delete)\n"
                     "And Many More features "
        )
        
        glass.add_text(panel_w//2, 250, instructions_text, 
                      ('Arial', 13), color='#fff3cd', 
                      anchor='center')
        
        button_frame = tk.Frame(glass, bg='gray20') 
        
        transaction_btn = tk.Button(button_frame, text="🔄 Transaction/Borrowers", font=('Arial', 14, 'bold'), 
                            bg='#3498db', fg='white', width=25, height=2, bd=0,
                            command=self.show_transaction_screen)
        transaction_btn.grid(row=0, column=0, padx=15, pady=10)
        
        admin_btn = tk.Button(button_frame, text="👨‍💼 Admin Panel", font=('Arial', 14), 
                             bg='#2ecc71', fg='white', width=20, height=2, bd=0,
                             command=self.create_admin_login_screen)
        admin_btn.grid(row=0, column=1, padx=15, pady=10)
        
        # ADDED: Team Credits Button
        team_btn = tk.Button(button_frame, text="🏆 Team Credits", font=('Arial', 14), 
                             bg='#9b59b6', fg='white', width=20, height=2, bd=0,
                             command=self.show_team_credits)
        team_btn.grid(row=0, column=2, padx=15, pady=10)
        
        glass.create_window(panel_w//2, 450, window=button_frame, anchor='center')
        
        stats = self.book_manager.get_statistics()
        stats_text = f"📊 Total Books: {stats['total_books']}|  Data Sync: ACTIVE | ⏳ Loading Spinner: READY | ⚡ Performance: OPTIMIZED"
        
        # ADDED: Footer with Team Credits
        footer_text = "📚 Library Management System | 👨‍💻 Developed and Architect by: RITUL DAS 2025| Date- 16-12-2025| B.A 3rd Semister" 
        glass.add_text(panel_w//2, 570, footer_text, 
                      ('Arial', 11, 'bold'), color='#bdc3c7')
        
        glass.add_text(panel_w//2, 550, stats_text, 
                      ('Arial', 12, 'bold'), color='#bdc3c7')

    # ==================== TEAM CREDITS WINDOW ====================
    def show_team_credits(self):
        """Show Team Credits window with 2 tabs"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🏆 Team Credits - Library Management System")
        dialog.geometry("900x600")
        dialog.configure(bg='#2c3e50')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the window
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        # Create notebook for tabs
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: 👨‍💻 DEVELOPER
        developer_tab = tk.Frame(notebook, bg='#34495e')
        notebook.add(developer_tab, text="👨‍💻 DEVELOPER")
        
        # Developer content
        dev_frame = tk.Frame(developer_tab, bg='#2c3e50', relief='solid', bd=2)
        dev_frame.place(relx=0.5, rely=0.5, anchor='center', width=800, height=500)
        
        # Developer photo/avatar placeholder
        photo_frame = tk.Frame(dev_frame, bg='#3498db', width=150, height=150)
        photo_frame.place(relx=0.5, y=100, anchor='center')
        photo_frame.pack_propagate(False)
        
        # Developer initials
        tk.Label(photo_frame, text="RD", font=('Arial', 36, 'bold'), 
                bg='#3498db', fg='white').pack(expand=True)
        
        # Developer info
        tk.Label(dev_frame, text="Developer-Ritul Das", 
                font=('Arial', 24, 'bold'), bg='#2c3e50', fg='white').place(relx=0.5, y=30, anchor='center')
        
        info_frame = tk.Frame(dev_frame, bg='#34495e')
        info_frame.place(relx=0.5, y=300, anchor='center', width=600, height=200)
        
        developer_info = [
            "NAME: Ritul Das",
            "ROLL NO: 2411162876", "SESSION : 2024-2028",
            "EMAIL: rituldas340@gmail.com",
            "PHONE: ++91 9365733141",
            "DEPARTMENT: English",           
            "Skills: Python, C++, HTML, CSS, JavaScript",
            "• Full-stack development",
            "• Database design & implementation",
            "• UI Design",
            
            
        ]
        
        for i, info in enumerate(developer_info):
            tk.Label(info_frame, text=info, font=('Arial', 12), 
                    bg='#34495e', fg='white', anchor='w').pack(fill='x', padx=20, pady=2)
        
        # Tab 2: ✏️ EDITORS
        editors_tab = tk.Frame(notebook, bg='#34495e')
        notebook.add(editors_tab, text="✏️EDITORS")
        
        # Create two columns for editors
        editor1_frame = tk.Frame(editors_tab, bg='#2c3e50', relief='solid', bd=2)
        editor1_frame.place(relx=0.25, rely=0.5, anchor='center', width=380, height=500)
        
        editor2_frame = tk.Frame(editors_tab, bg='#2c3e50', relief='solid', bd=2)
        editor2_frame.place(relx=0.75, rely=0.5, anchor='center', width=380, height=500)
        
        # Editor 1 content
        tk.Label(editor1_frame, text="Naba Jyoti Sarma", 
                font=('Arial', 20, 'bold'), bg='#2c3e50', fg='white').place(relx=0.5, y=30, anchor='center')
        
        # Editor 1 photo
        photo1_frame = tk.Frame(editor1_frame, bg='#e74c3c', width=120, height=120)
        photo1_frame.place(relx=0.5, y=100, anchor='center')
        photo1_frame.pack_propagate(False)
        tk.Label(photo1_frame, text="NJS", font=('Arial', 30, 'bold'), 
                bg='#e74c3c', fg='white').pack(expand=True)
        
        # Editor 1 info
        info1_frame = tk.Frame(editor1_frame, bg='#34495e')
        info1_frame.place(relx=0.5, y=280, anchor='center', width=300, height=180)
        
        editor1_info = [
            "NAME: Naba Jyoti Sarma",
            "ROLL NO: 2411121414",
            "DEPARTMENT: English"
            "EMAIL: sarmanayanjit8@gmail.com",
            "PHONE: +91  9487050167",
            "SESSION : 2024-2028",
            "RESPONSIBILITIES: Listing of Books",
            
        ]
        
        for i, info in enumerate(editor1_info):
            tk.Label(info1_frame, text=info, font=('Arial', 11), 
                    bg='#34495e', fg='white', anchor='w').pack(fill='x', padx=10, pady=1)
        
        # Editor 2 content
        tk.Label(editor2_frame, text="Syed Siyamuddin Ahmed ", 
                font=('Arial', 20, 'bold'), bg='#2c3e50', fg='white').place(relx=0.5, y=30, anchor='center')
        
        # Editor 2 photo
        photo2_frame = tk.Frame(editor2_frame, bg='#27ae60', width=120, height=120)
        photo2_frame.place(relx=0.5, y=100, anchor='center')
        photo2_frame.pack_propagate(False)
        tk.Label(photo2_frame, text="SSA", font=('Arial', 30, 'bold'), 
                bg='#27ae60', fg='white').pack(expand=True)
        
        # Editor 2 info
        info2_frame = tk.Frame(editor2_frame, bg='#34495e')
        info2_frame.place(relx=0.5, y=280, anchor='center', width=300, height=180)
        
        editor2_info = [
            "NAME: Syed Siyamuddin Ahmed",
            "ROLL NO: UA-241-033-0023",
            "DEPARTMENT: English"
            "EMAIL: siyamuddinahmed786@gmail.com" ,
            "PHONE: +91 8403892970",
            "SESSION : 2024-2028",
            "RESPONSIBILITIES: Listing of Books",
        ]
        
        for i, info in enumerate(editor2_info):
            tk.Label(info2_frame, text=info, font=('Arial', 11), 
                    bg='#34495e', fg='white', anchor='w').pack(fill='x', padx=10, pady=1)
        
        # Close button
        close_btn = tk.Button(dialog, text="Close", font=('Arial', 12), 
                            bg='#95a5a6', fg='white', width=20,
                            command=dialog.destroy)
        close_btn.pack(pady=10)

    # ==================== STOCK MANAGEMENT SYSTEM ====================
    def manage_stock(self):
        """Stock management interface"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        bg_path = "voting_bg.jpg"
        self.set_background(bg_path)
        
        panel_w, panel_h = 1200, 750
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path, radius=15)
        
        glass.add_text(panel_w//2, 40, "📦 Manage Stock - Library Inventory",  
                      ('Arial', 24, 'bold'), color='white')
        
        # Stats frame
        stats_frame = tk.Frame(glass, bg='#34495e', relief='raised', bd=2)
        stats_frame.place(relx=0.5, y=100, anchor='center', width=panel_w-100, height=60)
        
        out_of_stock = len(self.stock_manager.get_out_of_stock_books())
        low_stock = len(self.stock_manager.get_low_stock_books())
        in_stock = len(self.stock_manager.get_in_stock_books())
        
        stats_text = f"📊 STOCK STATUS: ⚠️ Out of Stock: {out_of_stock} | 🔶 Low Stock: {low_stock} | ✅ In Stock: {in_stock} | 📚 Total Books: {len(self.data.books)} | 🔄 Real-time Sync: ACTIVE | ⚡ Performance: OPTIMIZED"
        stats_label = tk.Label(stats_frame, text=stats_text,  
                              font=('Arial', 12, 'bold'), bg='#34495e', fg='white')
        stats_label.pack(expand=True, fill='both', padx=20, pady=10)
        
        # Notebook for sections
        notebook = ttk.Notebook(glass)
        notebook.place(relx=0.5, y=180, anchor='center', width=panel_w-100, height=450)
        
        # Tab 1: Out of Stock Books
        out_of_stock_tab = tk.Frame(notebook, bg='white')
        notebook.add(out_of_stock_tab, text="⚠️ OUT OF STOCK BOOKS")
        self.create_stock_section(out_of_stock_tab, "out_of_stock")
        
        # Tab 2: Low Stock Books
        low_stock_tab = tk.Frame(notebook, bg='white')
        notebook.add(low_stock_tab, text="🔶 LOW STOCK BOOKS")
        self.create_stock_section(low_stock_tab, "low_stock")
        
        # Tab 3: In Stock Books
        in_stock_tab = tk.Frame(notebook, bg='white')
        notebook.add(in_stock_tab, text="✅ IN STOCK BOOKS")
        self.create_stock_section(in_stock_tab, "in_stock")
        
        # Tab 4: Stock History
        history_tab = tk.Frame(notebook, bg='white')
        notebook.add(history_tab, text="📋 STOCK HISTORY")
        self.create_stock_history_tab(history_tab)
        
        # Action buttons
        action_frame = tk.Frame(glass, bg='gray20')
        action_frame.place(relx=0.5, y=660, anchor='center', width=panel_w-100, height=80)
        
        # Restock button
        restock_btn = tk.Button(action_frame, text="➕ Restock Single Book", font=('Arial', 11),
                               bg='#27ae60', fg='white',
                               command=self.restock_single_book_dialog)
        restock_btn.pack(side='left', padx=5, pady=5)
        
        # Bulk restock button
        bulk_restock_btn = tk.Button(action_frame, text="📥 Bulk Restock from Excel", font=('Arial', 11),
                                    bg='#f39c12', fg='white',
                                    command=self.bulk_restock_from_excel)
        bulk_restock_btn.pack(side='left', padx=5, pady=5)
        
        # View stock history button
        history_btn = tk.Button(action_frame, text="📋 View Stock History", font=('Arial', 11),
                               bg='#3498db', fg='white',
                               command=lambda: notebook.select(3))
        history_btn.pack(side='left', padx=5, pady=5)
        
        # Refresh button
        refresh_btn = tk.Button(action_frame, text="🔄 Refresh Stock", font=('Arial', 11),
                               bg='#9b59b6', fg='white',
                               command=lambda: [self.create_stock_section(out_of_stock_tab, "out_of_stock"),
                                               self.create_stock_section(low_stock_tab, "low_stock"),
                                               self.create_stock_section(in_stock_tab, "in_stock"),
                                               self.create_stock_history_tab(history_tab)])
        refresh_btn.pack(side='right', padx=5, pady=5)
        
        back_btn = tk.Button(glass, text="← Back to Admin Panel", font=('Arial', 12),  
                            bg='#6c757d', fg='white', command=self.create_admin_screen)
        glass.create_window(panel_w//2, panel_h-30, window=back_btn, anchor='center')
    
    def create_stock_section(self, parent, stock_type):
        """Create stock section treeview"""
        # Clear existing widgets
        for widget in parent.winfo_children():
            widget.destroy()
        
        # Create treeview with scrollbars
        tree_frame = tk.Frame(parent, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(tree_frame, orient='horizontal')
        h_scrollbar.pack(side='bottom', fill='x')
        
        # Create vertical scrollbar
        v_scrollbar = ttk.Scrollbar(tree_frame, orient='vertical')
        v_scrollbar.pack(side='right', fill='y')
        
        # Define columns
        columns = ("ID", "S.no", "Title", "Author", "ISBN", "Available", "Total", "Status", "Last Updated")
        
        # Create treeview
        tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show='headings',
            height=15,
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set
        )
        
        # Configure column widths
        col_widths = [50, 60, 200, 150, 120, 80, 80, 100, 120]
        for col, width in zip(columns, col_widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=50, stretch=False)
        
        # Configure scrollbars
        h_scrollbar.config(command=tree.xview)
        v_scrollbar.config(command=tree.yview)
        
        # Pack treeview
        tree.pack(side='left', fill='both', expand=True)
        
        # Load data based on stock type
        if stock_type == "out_of_stock":
            books = self.stock_manager.get_out_of_stock_books()
            section_title = "⚠️ OUT OF STOCK BOOKS (0 copies available)"
        elif stock_type == "low_stock":
            books = self.stock_manager.get_low_stock_books()
            section_title = "🔶 LOW STOCK BOOKS (3 or fewer copies)"
        else:  # in_stock
            books = self.stock_manager.get_in_stock_books()
            section_title = "✅ IN STOCK BOOKS (Normal stock)"
        
        # Add title
        title_label = tk.Label(parent, text=section_title, font=('Arial', 12, 'bold'),
                              bg='white', fg='#2c3e50')
        title_label.place(relx=0.5, y=10, anchor='center')
        
        # Insert data
        for book in books:
            status = self.stock_manager.get_book_stock_status(book['id'])
            tree.insert('', 'end', values=(
                book['id'],
                book.get('s.no_code', ''),
                book['title'],
                book['author'],
                book['isbn'],
                book['available_copies'],
                book['total_copies'],
                status,
                book.get('added_date', '')
            ))
        
        # Store tree reference for future use
        if stock_type == "out_of_stock":
            self.out_of_stock_tree = tree
            tree.bind('<Double-Button-1>', lambda e: self.restock_single_book_dialog())
        elif stock_type == "low_stock":
            self.low_stock_tree = tree
        else:
            self.in_stock_tree = tree
    
    def create_stock_history_tab(self, parent):
        """Create stock history tab"""
        # Clear existing widgets
        for widget in parent.winfo_children():
            widget.destroy()
        
        # Create treeview with scrollbars
        tree_frame = tk.Frame(parent, bg='white')
        tree_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(tree_frame, orient='horizontal')
        h_scrollbar.pack(side='bottom', fill='x')
        
        # Create vertical scrollbar
        v_scrollbar = ttk.Scrollbar(tree_frame, orient='vertical')
        v_scrollbar.pack(side='right', fill='y')
        
        # Define columns
        columns = ("History ID", "Book Title", "Author", "ISBN", "Action", "Qty Added", 
                  "Old Stock", "New Stock", "Source", "Timestamp", "Performed By")
        
        # Create treeview
        history_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show='headings',
            height=15,
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set
        )
        
        # Configure column widths
        col_widths = [80, 200, 150, 120, 80, 80, 80, 80, 100, 150, 100]
        for col, width in zip(columns, col_widths):
            history_tree.heading(col, text=col)
            history_tree.column(col, width=width, minwidth=50, stretch=False)
        
        # Configure scrollbars
        h_scrollbar.config(command=history_tree.xview)
        v_scrollbar.config(command=history_tree.yview)
        
        # Pack treeview
        history_tree.pack(side='left', fill='both', expand=True)
        
        # Load stock history
        stock_history = self.stock_manager.get_stock_history()
        
        # Add title
        title_label = tk.Label(parent, text="📋 STOCK HISTORY - All stock movements", 
                              font=('Arial', 12, 'bold'), bg='white', fg='#2c3e50')
        title_label.place(relx=0.5, y=10, anchor='center')
        
        # Insert data (most recent first)
        for record in reversed(stock_history):
            history_tree.insert('', 'end', values=(
                record['history_id'],
                record['book_title'],
                record['book_author'],
                record['book_isbn'],
                record['action'],
                record['quantity_added'],
                record['old_stock'],
                record['new_stock'],
                record['source'],
                record['timestamp'],
                record['performed_by']
            ))
        
        self.stock_history_tree = history_tree
    
    def restock_single_book_dialog(self):
        """Dialog to restock a single book"""
        # Check if we have a selected book from out_of_stock_tree
        selected_item = None
        if hasattr(self, 'out_of_stock_tree'):
            selection = self.out_of_stock_tree.selection()
            if selection:
                selected_item = self.out_of_stock_tree.item(selection[0])
        
        # If no selection, show all books
        dialog = tk.Toplevel(self.root)
        dialog.title("➕ Restock Book")
        dialog.geometry("500x400")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="➕ Restock Book",  
                 font=('Arial', 16, 'bold'), bg='white', fg='#2c3e50').pack(pady=20)
        
        # Book selection
        selection_frame = tk.Frame(dialog, bg='white')
        selection_frame.pack(fill='both', expand=True, padx=30, pady=10)
        
        tk.Label(selection_frame, text="Select Book to Restock:", font=('Arial', 11, 'bold'), 
                bg='white').grid(row=0, column=0, sticky='w', pady=5)
        
        # Create book selection combobox
        book_var = tk.StringVar()
        book_options = []
        book_dict = {}
        
        # Get out of stock books first
        out_of_stock_books = self.stock_manager.get_out_of_stock_books()
        for book in out_of_stock_books:
            display_text = f"{book['title']} by {book['author']} (ISBN: {book['isbn']}) - ⚠️ OUT OF STOCK"
            book_options.append(display_text)
            book_dict[display_text] = book
        
        # Get low stock books
        low_stock_books = self.stock_manager.get_low_stock_books()
        for book in low_stock_books:
            display_text = f"{book['title']} by {book['author']} (ISBN: {book['isbn']}) - 🔶 LOW STOCK: {book['available_copies']} copies"
            book_options.append(display_text)
            book_dict[display_text] = book
        
        # Get all books
        for book in self.data.books:
            if book not in out_of_stock_books and book not in low_stock_books:
                display_text = f"{book['title']} by {book['author']} (ISBN: {book['isbn']}) - ✅ {book['available_copies']} copies"
                book_options.append(display_text)
                book_dict[display_text] = book
        
        book_combo = ttk.Combobox(selection_frame, textvariable=book_var, 
                                 values=book_options, width=50)
        book_combo.grid(row=1, column=0, columnspan=2, pady=5, sticky='ew')
        
        # If we have a selected item from tree, preselect it
        if selected_item:
            values = selected_item['values']
            isbn = values[4]  # ISBN is at index 4
            for option in book_options:
                if isbn in option:
                    book_combo.set(option)
                    break
        
        # Quantity
        tk.Label(selection_frame, text="Quantity to Add:", font=('Arial', 11, 'bold'), 
                bg='white').grid(row=2, column=0, sticky='w', pady=(10, 5))
        
        quantity_var = tk.StringVar(value="5")
        quantity_entry = tk.Entry(selection_frame, textvariable=quantity_var, 
                                 font=('Arial', 11), width=10)
        quantity_entry.grid(row=2, column=1, pady=(10, 5), sticky='w')
        
        # Source
        tk.Label(selection_frame, text="Source:", font=('Arial', 11), 
                bg='white').grid(row=3, column=0, sticky='w', pady=5)
        
        source_var = tk.StringVar(value="Purchase")
        source_combo = ttk.Combobox(selection_frame, textvariable=source_var,
                                   values=["Purchase", "Donation", "Transfer", "Other"])
        source_combo.grid(row=3, column=1, pady=5, sticky='w')
        
        # Notes
        tk.Label(selection_frame, text="Notes (Optional):", font=('Arial', 11), 
                bg='white').grid(row=4, column=0, sticky='w', pady=5)
        
        notes_var = tk.StringVar()
        notes_entry = tk.Entry(selection_frame, textvariable=notes_var, 
                              font=('Arial', 11), width=30)
        notes_entry.grid(row=4, column=1, pady=5, sticky='w')
        
        def perform_restock():
            """Perform the restocking"""
            selected_book_text = book_var.get()
            if not selected_book_text:
                messagebox.showerror("Error", "Please select a book")
                return
            
            if selected_book_text not in book_dict:
                messagebox.showerror("Error", "Invalid book selection")
                return
            
            try:
                quantity = int(quantity_var.get())
                if quantity <= 0:
                    messagebox.showerror("Error", "Quantity must be positive")
                    return
            except:
                messagebox.showerror("Error", "Please enter valid quantity")
                return
            
            source = source_var.get()
            notes = notes_var.get()
            
            book = book_dict[selected_book_text]
            
            # Show loading spinner
            self.loading_spinner.show(f"Saving {quantity} copies of '{book['title']}'...")
            self.root.update()
            
            try:
                # Restock the book using observable pattern
                success, updated_book = self.stock_manager.restock_book(
                    book_id=book['id'],
                    quantity=quantity,
                    source=source,
                    notes=notes
                )
                
                if success:
                    # Notify observers of the change
                    self.book_observable.notify_data_change('BOOK_STOCK_UPDATED', book['id'], {
                        'old_stock': updated_book['available_copies'] - quantity,
                        'new_stock': updated_book['available_copies'],
                        'old_total': updated_book['total_copies'] - quantity,
                        'new_total': updated_book['total_copies'],
                        'book_title': updated_book['title'],
                        'book_author': updated_book['author']
                    })
                    
                    # Clear cache
                    self.data.book_cache.clear()
                    
                    # Hide spinner
                    self.loading_spinner.hide()
                    
                    messagebox.showinfo("Success", 
                                      f"✅ Book restocked successfully!\n\n"
                                      f"📚 Book: {book['title']}\n"
                                      f"✍️ Author: {book['author']}\n"
                                      f"📦 Quantity Added: {quantity} copies\n"
                                      f"💰 Source: {source}\n"
                                      f"📝 Notes: {notes if notes else 'None'}\n\n"
                                      f"📊 New Stock: {book['available_copies'] + quantity} copies")
                    
                    # Refresh stock views using observer pattern
                    dialog.destroy()
                    # UI will be refreshed automatically by the UIUpdater observer
                else:
                    self.loading_spinner.hide()
                    messagebox.showerror("Error", "Failed to restock book")
            except Exception as e:
                self.loading_spinner.hide()
                messagebox.showerror("Error", f"Failed to save to database:\n\n{str(e)}")
        
        # Buttons
        button_frame = tk.Frame(dialog, bg='white')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Add Stock", font=('Arial', 12),  
                  bg='#27ae60', fg='white', command=perform_restock).pack(side='left', padx=5)
        tk.Button(button_frame, text="Cancel", font=('Arial', 12),  
                  bg='#95a5a6', fg='white', command=dialog.destroy).pack(side='left', padx=5)
        
        book_combo.focus()
    
    def bulk_restock_from_excel(self):
        """Bulk restock from Excel file"""
        # Ask for Excel file
        file_path = filedialog.askopenfilename(
            title="Select Excel file for bulk restock",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        # Confirm bulk restock
        if not messagebox.askyesno("Confirm Bulk Restock", 
                                  "⚠️ BULK RESTOCK CONFIRMATION\n\n"
                                  "This will add stock to multiple books from Excel file.\n\n"
                                  "Excel format required:\n"
                                  "• Column A: ISBN\n"
                                  "• Column B: Quantity to add\n\n"
                                  "Do you want to continue?"):
            return
        
        # Show loading spinner
        self.loading_spinner.show("Processing bulk restock from Excel...")
        self.root.update()
        
        try:
            # Perform bulk restock
            success = self.stock_manager.bulk_restock_from_excel(file_path)
            
            if success:
                # Clear cache
                self.data.book_cache.clear()
                
                # Notify observers of bulk changes
                for book in self.data.books:
                    self.book_observable.notify_data_change('BOOK_STOCK_UPDATED', book['id'], {
                        'book_title': book['title'],
                        'book_author': book['author']
                    })
                
                # Hide spinner
                self.loading_spinner.hide()
                
                # Refresh stock views
                self.manage_stock()
            else:
                self.loading_spinner.hide()
        except Exception as e:
            self.loading_spinner.hide()
            messagebox.showerror("Error", f"Failed to process bulk restock:\n\n{str(e)}")
    
    # ==================== FEATURE 1: SMART BOOK SEARCH ====================
    def create_smart_book_search(self, parent_widget, entry_var):
        """Create smart book search dropdown for book entry"""
        # Create frame for dropdown
        self.suggestion_frame = tk.Frame(parent_widget, bg='white', relief='solid', bd=1)
        self.suggestion_frame.place_forget()  # Initially hidden
        
        # Create listbox for suggestions
        self.suggestion_listbox = tk.Listbox(
            self.suggestion_frame, 
            height=6, 
            font=('Arial', 10),
            bg='white',
            selectmode='single'
        )
        self.suggestion_listbox.pack(fill='both', expand=True)
        
        # Position dropdown below entry
        entry_widget = None
        for widget in parent_widget.winfo_children():
            if isinstance(widget, tk.Entry) and str(widget.cget('textvariable')) == str(entry_var):
                entry_widget = widget
                break
        
        if entry_widget:
            entry_widget.bind('<KeyRelease>', self.update_smart_suggestions)
            entry_widget.bind('<FocusOut>', lambda e: self.hide_smart_suggestions())
        
        # Bind selection
        self.suggestion_listbox.bind('<<ListboxSelect>>', self.select_smart_suggestion)
        
        return self.suggestion_listbox
    
    def update_smart_suggestions(self, event):
        """Update smart suggestion list based on typed text"""
        search_text = event.widget.get()
        
        if not hasattr(self, 'suggestion_listbox'):
            return
        
        # Clear current suggestions
        self.suggestion_listbox.delete(0, tk.END)
        
        if not search_text.strip():
            self.suggestion_frame.place_forget()
            return
        
        # Use fast search from book_lookup
        search_results = self.data.book_lookup.search_by_text(search_text)
        
        if not search_results:
            self.suggestion_frame.place_forget()
            return
        
        # Show suggestions (max 6)
        for book in search_results[:6]:
            # Determine availability color
            if book['available_copies'] <= 0:
                color = "red"
                status = "⚠️ OUT OF STOCK"
            elif book['available_copies'] <= 2:
                color = "orange"
                status = "🔶 LOW STOCK"
            else:
                color = "green"
                status = "✅ Available"
            
            display_text = f"{book['title']} by {book['author']} - {book['available_copies']} copies ({status})"
            
            self.suggestion_listbox.insert(tk.END, display_text)
            # Set color based on availability
            idx = self.suggestion_listbox.size() - 1
            if color == "green":
                self.suggestion_listbox.itemconfig(idx, {'fg': 'green'})
            elif color == "orange":
                self.suggestion_listbox.itemconfig(idx, {'fg': 'orange'})
            else:
                self.suggestion_listbox.itemconfig(idx, {'fg': 'red'})
        
        # Show dropdown
        x = event.widget.winfo_x()
        y = event.widget.winfo_y() + event.widget.winfo_height()
        width = event.widget.winfo_width()
        
        self.suggestion_frame.place(x=x, y=y, width=width)
        self.suggestion_frame.lift()
    
    def select_smart_suggestion(self, event):
        """When user selects a suggestion"""
        if not self.suggestion_listbox.curselection():
            return
        
        selected_index = self.suggestion_listbox.curselection()[0]
        selected_text = self.suggestion_listbox.get(selected_index)
        
        # Use fast lookup by title
        book_title = selected_text.split(' by ')[0] if ' by ' in selected_text else selected_text
        book = self.data.book_lookup.get_by_title(book_title)
        
        if book:
            # Auto-fill the form
            if hasattr(self, 'book_name_var'):
                self.book_name_var.set(book['title'])
            if hasattr(self, 'book_author_var'):
                self.book_author_var.set(book['author'])
            if hasattr(self, 'isbn_code_var'):
                self.isbn_code_var.set(book['isbn'])
            
            # Show availability status
            if hasattr(self, 'validation_label'):
                if book['available_copies'] <= 0:
                    self.validation_label.config(
                        text="❌ This book is OUT OF STOCK and cannot be issued!", 
                        fg='red'
                    )
                elif book['available_copies'] <= 2:
                    self.validation_label.config(
                        text=f"⚠️ LOW STOCK: Only {book['available_copies']} copies available", 
                        fg='orange'
                    )
                else:
                    self.validation_label.config(
                        text=f"✅ {book['available_copies']} copies available", 
                        fg='green'
                    )
        
        self.hide_smart_suggestions()
    
    def hide_smart_suggestions(self):
        """Hide smart suggestion dropdown"""
        if hasattr(self, 'suggestion_frame'):
            self.suggestion_frame.place_forget()

    # ==================== FEATURE 2: OUT OF STOCK LIST RESTOCK ====================
    def show_out_of_stock_restock(self):
        """Show out of stock books with restock buttons"""
        dialog = tk.Toplevel(self.root)
        dialog.title("⚠️ Out of Stock Books - Restock")
        dialog.geometry("900x600")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="⚠️ OUT OF STOCK BOOKS - RESTOCK",  
                 font=('Arial', 18, 'bold'), bg='white', fg='#2c3e50').pack(pady=20)
        
        # Get out of stock books
        out_of_stock_books = self.stock_manager.get_out_of_stock_books()
        
        if not out_of_stock_books:
            tk.Label(dialog, text="✅ All books are in stock!",  
                     font=('Arial', 14), bg='white', fg='green').pack(pady=50)
            tk.Button(dialog, text="Close", font=('Arial', 12),  
                      bg='#95a5a6', fg='white', command=dialog.destroy).pack(pady=20)
            return
        
        # Create scrollable frame
        canvas = tk.Canvas(dialog, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient='vertical', command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='white')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Add books with restock buttons
        for i, book in enumerate(out_of_stock_books):
            book_frame = tk.Frame(scrollable_frame, bg='#fff3cd' if i % 2 == 0 else '#fffde7', 
                                 relief='solid', bd=1)
            book_frame.pack(fill='x', padx=20, pady=5)
            
            # Book info
            info_label = tk.Label(
                book_frame, 
                text=f"{book['title']} | {book['author']} | ISBN: {book['isbn']} | 0 copies",
                font=('Arial', 11),
                bg='#fff3cd' if i % 2 == 0 else '#fffde7',
                anchor='w'
            )
            info_label.pack(side='left', fill='x', expand=True, padx=10, pady=10)
            
            # Restock button
            restock_btn = tk.Button(
                book_frame, 
                text="➕ Update",
                font=('Arial', 10, 'bold'),
                bg='#27ae60',
                fg='white',
                command=lambda b=book: self.restock_single_book_popup(b, dialog)
            )
            restock_btn.pack(side='right', padx=10, pady=10)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=10)
        scrollbar.pack(side="right", fill="y")
        
        # Stats
        stats_label = tk.Label(
            dialog, 
            text=f"📊 Total Out of Stock Books: {len(out_of_stock_books)}",
            font=('Arial', 12, 'bold'),
            bg='white',
            fg='#2c3e50'
        )
        stats_label.pack(pady=10)
        
        tk.Button(dialog, text="Close", font=('Arial', 12),  
                  bg='#95a5a6', fg='white', command=dialog.destroy).pack(pady=10)
    
    def restock_single_book_popup(self, book, parent_dialog=None):
        """Popup to restock a single out of stock book"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Update Stock: {book['title']}")
        dialog.geometry("400x300")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="➕ Update Stock",  
                 font=('Arial', 16, 'bold'), bg='white', fg='#2c3e50').pack(pady=20)
        
        tk.Label(dialog, text=f"Book: {book['title']}",  
                 font=('Arial', 12), bg='white').pack(pady=5)
        
        tk.Label(dialog, text=f"Current: 0 copies",  
                 font=('Arial', 12), bg='white', fg='red').pack(pady=5)
        
        # Quantity input
        tk.Label(dialog, text="Add:",  
                 font=('Arial', 12), bg='white').pack(pady=10)
        
        quantity_var = tk.StringVar(value="1")
        quantity_entry = tk.Entry(dialog, textvariable=quantity_var, 
                                 font=('Arial', 14), width=10, justify='center')
        quantity_entry.pack(pady=5)
        quantity_entry.focus()
        quantity_entry.select_range(0, tk.END)
        
        def save_restock():
            """Save the restock"""
            try:
                quantity_text = quantity_var.get().strip()
                if not quantity_text:
                    quantity = 1  # Default to 1 if blank
                else:
                    quantity = int(quantity_text)
                    if quantity <= 0:
                        messagebox.showerror("Error", "Quantity must be positive")
                        return
            except:
                messagebox.showerror("Error", "Please enter valid number")
                return
            
            # Show loading spinner
            self.loading_spinner.show(f"Updating stock for '{book['title']}'...")
            self.root.update()
            
            try:
                # Restock the book using observable pattern
                success, updated_book = self.stock_manager.restock_book(
                    book_id=book['id'],
                    quantity=quantity,
                    source="Manual Restock",
                    notes="Restocked from out of stock list"
                )
                
                if success:
                    # Clear cache
                    self.data.book_cache.clear()
                    
                    # Notify observers of the change
                    self.book_observable.notify_data_change('BOOK_STOCK_UPDATED', book['id'], {
                        'old_stock': 0,
                        'new_stock': updated_book['available_copies'],
                        'old_total': updated_book['total_copies'] - quantity,
                        'new_total': updated_book['total_copies'],
                        'book_title': updated_book['title'],
                        'book_author': updated_book['author']
                    })
                    
                    # Hide spinner
                    self.loading_spinner.hide()
                    
                    messagebox.showinfo("Success", 
                                      f"✅ Book restocked successfully!\n\n"
                                      f"📚 Book: {book['title']}\n"
                                      f"📦 Quantity Added: {quantity} copies\n"
                                      f"📊 New Stock: {quantity} copies")
                    
                    dialog.destroy()
                    
                    # Refresh the out of stock list if parent dialog exists
                    if parent_dialog and parent_dialog.winfo_exists():
                        parent_dialog.destroy()
                        self.show_out_of_stock_restock()
                    else:
                        # Refresh admin screen if needed (handled by observer)
                        pass
                else:
                    self.loading_spinner.hide()
                    messagebox.showerror("Error", "Failed to restock book")
            except Exception as e:
                self.loading_spinner.hide()
                messagebox.showerror("Error", f"Failed to save to database:\n\n{str(e)}")
        
        # Buttons
        button_frame = tk.Frame(dialog, bg='white')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Save", font=('Arial', 12),  
                  bg='#27ae60', fg='white', command=save_restock).pack(side='left', padx=10)
        tk.Button(button_frame, text="Cancel", font=('Arial', 12),  
                  bg='#95a5a6', fg='white', command=dialog.destroy).pack(side='left', padx=10)

    # ==================== TRANSACTION/BORROWERS SCREEN ====================
    def show_transaction_screen(self):
        """Transaction and Borrowers management screen"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        bg_path = "voting_bg.jpg"
        self.set_background(bg_path)
        
        panel_w, panel_h = 1150, 750
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path, radius=5)
        
        glass.add_text(panel_w//2, 40, "🔄 Transaction Management",  
                      ('Arial', 24, 'bold'), color='white')
        
        notebook = ttk.Notebook(self.root)
        notebook.place(relx=0.5, y=80, anchor='n', width=panel_w-100, height=panel_h-130)
        
        issue_tab_frame = tk.Frame(notebook, bg='white')
        notebook.add(issue_tab_frame, text="📖 Issue Book")
        
        self.create_issue_tab(issue_tab_frame)
        
        # I'm keeping the save button but changing its functionality
        save_btn_frame = tk.Frame(self.root, bg='gray20')
        save_btn_frame.place(relx=0.95, rely=0.05, anchor='ne')
        
        # Changed text to indicate real SQLite3 saving
        save_btn = tk.Button(save_btn_frame, text="💾 REAL-TIME SQLite3 SAVE",  
                            font=('Arial', 11, 'bold'), 
                            bg='#27ae60', fg='white',  # Changed to green to indicate real saving
                            padx=15, pady=8,
                            command=self.save_real_data_to_sqlite)  # Changed to real save function
        save_btn.pack()
        
        back_btn = tk.Button(glass, text="← Back to Main", font=('Arial', 12),  
                            bg='#6c757d', fg='white', command=self.create_welcome_screen)
        glass.create_window(panel_w//2, panel_h-50, window=back_btn, anchor='center')
    
    def save_real_data_to_sqlite(self):
        """Save REAL transaction data directly to SQLite3 database"""
        try:
            current_time = datetime.now()
            
            # GET ACTUAL FORM DATA FROM FORM FIELDS
            student_name = self.student_name_var.get().strip()
            phone = self.phone_var.get().strip()
            #email = self.email_var.get().strip()  # NEW: Get email - REMOVED
            book_name = self.book_name_var.get().strip()
            book_author = self.book_author_var.get().strip()
            isbn_code = self.isbn_code_var.get().strip()
            
            # Validate required fields
            if not student_name:
                messagebox.showerror("Validation Error", "Please enter Student Name")
                self.student_name_entry.focus()
                return
                
            #if not email:
            #    messagebox.showerror("Validation Error", "Please enter Email Address")
            #    self.email_entry.focus()
            #    return
                
            #if '@' not in email or '.' not in email:
            #    messagebox.showerror("Validation Error", "Please enter valid email address")
            #    self.email_entry.focus()
            #    return
                
            if not book_name:
                messagebox.showerror("Validation Error", "Please enter Book Title")
                self.book_name_entry.focus()
                return
                
            if not book_author:
                messagebox.showerror("Validation Error", "Please enter Book Author")
                self.book_author_entry.focus()
                return
                
            if not isbn_code:
                messagebox.showerror("Validation Error", "Please enter ISBN Code")
                self.isbn_code_entry.focus()
                return
            
            # Use empty string if phone not provided
            if not phone:
                phone = ""
            
            # Show loading spinner
            self.loading_spinner.show("Saving to SQLite3 database...")
            self.root.update()
            
            try:
                # Create REAL transaction data USING ACTUAL FORM VALUES
                real_save = {
                    "transaction_id": len(self.data.transactions) + 1,
                    "save_timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "transaction_type": "real_time_issue",
                    "student_name": student_name,  # ACTUAL student name from form
                    "student_phone": phone,  # ACTUAL phone from form
                    #"student_email": email,  # NEW: Email from form - REMOVED
                    #"email_sent": 0,  # NEW: Email status - REMOVED
                    "member_id": f"M{len(self.data.members) + 1:04d}",
                    "member_name": student_name,  # ACTUAL student name from form
                    "member_type": "Student",
                    "book_id": len(self.data.books) + 1,
                    "book_title": book_name,  # ACTUAL book title from form
                    "book_author": book_author,  # ACTUAL author from form
                    "book_isbn": isbn_code,  # ACTUAL ISBN from form
                    "book_category": "General",
                    "issue_date": current_time.strftime("%Y-%m-%d"),
                    "due_date": (current_time + timedelta(days=14)).strftime("%Y-%m-%d"),
                    "return_date": "",
                    "status": "issued",  # This will appear in Active Borrowers
                    "fine_amount": 0,
                    "fine_paid": 0,
                    "renewals": 0,
                    "issue_timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                save_id = self.data.add_admin_save_sqlite(real_save)
                
                # Also create real book and member entries USING ACTUAL FORM DATA
                new_book_id = len(self.data.books) + 1
                new_book = {
                    "id": new_book_id,
                    "s.no_code": f"T{new_book_id}",  # Add s.no_code
                    "title": book_name,  # ACTUAL book title from form
                    "author": book_author,  # ACTUAL author from form
                    "isbn": isbn_code,  # ACTUAL ISBN from form
                    "category": "General",
                    "publisher": "Unknown",
                    "publication_year": str(current_time.year),
                    "page_count": 300,
                    "price": 500,
                    "total_copies": 1,
                    "available_copies": 0,
                    "shelf_location": "A1",
                    "description": f"Book '{book_name}' by {book_author}",
                    "added_date": current_time.strftime("%Y-%m-%d")
                }
                self.data.books.append(new_book)
                
                new_member_id = f"M{len(self.data.members) + 1:04d}"
                new_member = {
                    "id": new_member_id,
                    "name": student_name,  # ACTUAL student name from form
                    #"email": email,  # ACTUAL email from form - REMOVED
                    "phone": phone,  # ACTUAL phone from form
                    "address": "Address not provided",
                    "membership_type": "Student",
                    "membership_date": current_time.strftime("%Y-%m-%d"),
                    "max_books": 5,
                    "active": True,
                    "total_borrowed": 1,
                    "current_borrowed": 1,
                    "join_date": current_time.strftime("%Y-%m-%d")
                }
                self.data.members.append(new_member)
                
                new_transaction_id = len(self.data.transactions) + 1
                new_transaction = {
                    "id": new_transaction_id,
                    "book_id": new_book_id,
                    "member_id": new_member_id,
                    "issue_date": current_time.strftime("%Y-%m-%d"),
                    "due_date": (current_time + timedelta(days=14)).strftime("%Y-%m-%d"),
                    "return_date": "",
                    "status": "issued",
                    "fine_amount": 0,
                    "fine_paid": False,
                    "renewals": 0
                }
                self.data.transactions.append(new_transaction)
                
                # Clear cache
                self.data.book_cache.clear()
                self.data.book_lookup.build_index(self.data.books)
                
                self.data.save_data()
                
                self.history_manager.add_to_history(new_transaction_id, new_book_id, new_member_id, "real_issued")
                
                # Hide spinner
                self.loading_spinner.hide()
                
                messagebox.showinfo("REAL DATA SAVED", 
                                  f"✅ Real transaction data saved to SQLite3 database!\n\n"
                                  f"📋 REAL TRANSACTION DETAILS:\n"
                                  f"──────────────────────────────\n"
                                  f"🔢 Save ID: {save_id}\n"
                                  f"📅 Timestamp: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                  f"👤 Student: {student_name}\n"
                                  f"� Phone: {phone if phone else 'Not provided'}\n"
                                  f"📚 Book: {book_name}\n"
                                  f"✍️ Author: {book_author}\n"
                                  f"#️⃣ ISBN: {isbn_code}\n"
                                  f"📅 Issue Date: {current_time.strftime('%Y-%m-%d')}\n"
                                  f"⏰ Due Date: {(current_time + timedelta(days=14)).strftime('%Y-%m-%d')}\n\n"
                                  f"💾 Data saved to SQLite3 database in real-time!\n"
                                  f"📋 This will appear in Active Borrowers section.\n"
                                  f"⚡ Performance: Optimized with caching")
                
                debug_sqlite_connection()
                
            except Exception as e:
                self.loading_spinner.hide()
                error_msg = f"❌ Real data save failed:\n\n{str(e)}"
                messagebox.showerror("REAL DATA ERROR", error_msg)
            
        except Exception as e:
            self.loading_spinner.hide()
            error_msg = f"❌ Real data save failed:\n\n{str(e)}"
            messagebox.showerror("REAL DATA ERROR", error_msg)
    
    def create_issue_tab(self, parent):
        """Create issue book tab with SMART BOOK SEARCH feature"""
        self.clock_running = False
        
        main_container = tk.Frame(parent, bg='white')
        main_container.pack(fill='both', expand=True, padx=20, pady=10)
        
        clock_frame = tk.Frame(main_container, bg='#e8f4f8', relief='groove', bd=2)
        clock_frame.pack(fill='x', pady=(0, 20))
        
        tk.Label(clock_frame, text="🕐 CURRENT DATE & TIME", 
                font=('Arial', 14, 'bold'), bg='#e8f4f8', fg='#2c3e50').pack(pady=(10, 5))
        
        self.current_time_label = tk.Label(clock_frame, text="", 
                                          font=('Arial', 16, 'bold'), bg='#e8f4f8', fg='#e74c3c')
        self.current_time_label.pack(pady=(0, 10))
        
        form_container = tk.Frame(main_container, bg='white')
        form_container.pack(fill='both', expand=True, pady=10)
        
        left_column = tk.Frame(form_container, bg='white')
        left_column.pack(side='left', fill='both', expand=True, padx=(0, 10))
        
        right_column = tk.Frame(form_container, bg='white')
        right_column.pack(side='right', fill='both', expand=True, padx=(10, 0))
        
        borrower_frame = tk.Frame(left_column, bg='#f9f9f9', relief='ridge', bd=2)
        borrower_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        tk.Label(borrower_frame, text="👤 BORROWER INFORMATION", 
                font=('Arial', 14, 'bold'), bg='#f9f9f9', fg='#2c3e50').pack(pady=(10, 15))
        
        tk.Label(borrower_frame, text="Student Name *", font=('Arial', 11, 'bold'), 
                bg='#f9f9f9', fg='#555').pack(anchor='w', padx=20, pady=(5, 0))
        
        self.student_name_var = tk.StringVar()
        self.student_name_entry = tk.Entry(borrower_frame, textvariable=self.student_name_var, 
                                          font=('Arial', 12), width=35, bg='white',
                                          relief='solid', bd=1)
        self.student_name_entry.pack(fill='x', padx=20, pady=(5, 15))
        
        #tk.Label(borrower_frame, text="Email Address *", font=('Arial', 11, 'bold'),  # NEW: Email field - REMOVED
        #        bg='#f9f9f9', fg='#555').pack(anchor='w', padx=20, pady=(5, 0))
        
        #self.email_var = tk.StringVar()  # NEW: Email variable - REMOVED
        #self.email_entry = tk.Entry(borrower_frame, textvariable=self.email_var, 
        #                           font=('Arial', 12), width=35, bg='white',
        #                           relief='solid', bd=1)
        #self.email_entry.pack(fill='x', padx=20, pady=(5, 15))
        
        tk.Label(borrower_frame, text="Phone No. (Optional)", font=('Arial', 11), 
                bg='#f9f9f9', fg='#555').pack(anchor='w', padx=20, pady=(5, 0))
        
        self.phone_var = tk.StringVar()
        self.phone_entry = tk.Entry(borrower_frame, textvariable=self.phone_var, 
                                   font=('Arial', 12), width=35, bg='white',
                                   relief='solid', bd=1)
        self.phone_entry.pack(fill='x', padx=20, pady=(5, 15))
        
        book_frame = tk.Frame(right_column, bg='#f9f9f9', relief='ridge', bd=2)
        book_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        tk.Label(book_frame, text="📚 BOOK INFORMATION", 
                font=('Arial', 14, 'bold'), bg='#f9f9f9', fg='#2c3e50').pack(pady=(10, 15))
        
        # 🔥 FEATURE 1: SMART BOOK SEARCH - Dropdown for niche
        tk.Label(book_frame, text="Book Title *", font=('Arial', 11, 'bold'), 
                bg='#f9f9f9', fg='#555').pack(anchor='w', padx=20, pady=(5, 0))
        
        self.book_name_var = tk.StringVar()
        self.book_name_entry = tk.Entry(book_frame, textvariable=self.book_name_var, 
                                       font=('Arial', 12), width=35, bg='white',
                                       relief='solid', bd=1)
        self.book_name_entry.pack(fill='x', padx=20, pady=(5, 5))
        
        # 🔥 Create smart book search dropdown
        self.create_smart_book_search(book_frame, self.book_name_var)
        
        tk.Label(book_frame, text="Author *", font=('Arial', 11, 'bold'), 
                bg='#f9f9f9', fg='#555').pack(anchor='w', padx=20, pady=(5, 0))
        
        self.book_author_var = tk.StringVar()
        self.book_author_entry = tk.Entry(book_frame, textvariable=self.book_author_var, 
                                         font=('Arial', 12), width=35, bg='white',
                                         relief='solid', bd=1)
        self.book_author_entry.pack(fill='x', padx=20, pady=(5, 15))
        
        tk.Label(book_frame, text="ISBN *", font=('Arial', 11, 'bold'), 
                bg='#f9f9f9', fg='#555').pack(anchor='w', padx=20, pady=(5, 0))
        
        self.isbn_code_var = tk.StringVar()
        self.isbn_code_entry = tk.Entry(book_frame, textvariable=self.isbn_code_var, 
                                       font=('Arial', 12), width=35, bg='white',
                                       relief='solid', bd=1)
        self.isbn_code_entry.pack(fill='x', padx=20, pady=(5, 15))
        
        # Add notification section for email reminders - REMOVED
        #notification_frame = tk.Frame(main_container, bg='#fff3cd', relief='solid', bd=1)
        #notification_frame.pack(fill='x', pady=(10, 0))
        
        #notification_text = "📧 EMAIL NOTIFICATIONS: Instant email on issue + Auto-reminders on Day 5, 10, 15 at 9 AM"
        #tk.Label(notification_frame, text=notification_text, 
        #        font=('Arial', 10, 'bold'), bg='#fff3cd', fg='#856404').pack(pady=5)
        
        date_section = tk.Frame(main_container, bg='white')
        date_section.pack(fill='x', pady=20)
        
        date_container = tk.Frame(date_section, bg='#2c3e50', relief='raised', bd=2)
        date_container.pack(fill='x')
        
        tk.Label(date_container, text="📅 ISSUE & DUE DATES (AUTOMATIC)", 
                font=('Arial', 14, 'bold'), bg='#2c3e50', fg='white').pack(pady=(10, 15))
        
        date_columns = tk.Frame(date_container, bg='#2c3e50')
        date_columns.pack(pady=(0, 15))
        
        issue_col = tk.Frame(date_columns, bg='#2c3e50')
        issue_col.pack(side='left', padx=30)
        
        tk.Label(issue_col, text="Issue Date", 
                font=('Arial', 12, 'bold'), bg='#2c3e50', fg='#bdc3c7').pack()
        self.issue_date_label = tk.Label(issue_col, text="", 
                                        font=('Arial', 14, 'bold'), bg='#2c3e50', fg='white')
        self.issue_date_label.pack(pady=5)
        
        due_col = tk.Frame(date_columns, bg='#2c3e50')
        due_col.pack(side='left', padx=30)
        
        tk.Label(due_col, text="Due Date (14 days)", 
                font=('Arial', 12, 'bold'), bg='#2c3e50', fg='#bdc3c7').pack()
        self.due_date_label = tk.Label(due_col, text="", 
                                      font=('Arial', 14, 'bold'), bg='#2c3e50', fg='#ff9999')
        self.due_date_label.pack(pady=5)
        
        # Add email notification reminder - REMOVED
        #reminder_col = tk.Frame(date_columns, bg='#2c3e50')
        #reminder_col.pack(side='left', padx=30)
        
        #tk.Label(reminder_col, text="Email Reminders", 
        #        font=('Arial', 12, 'bold'), bg='#2c3e50', fg='#bdc3c7').pack()
        #reminder_label = tk.Label(reminder_col, text="Day 5, 10, 15\n9 AM Daily", 
        #                         font=('Arial', 11, 'bold'), bg='#2c3e50', fg='#4dabf7',
        #                         justify='center')
        #reminder_label.pack(pady=5)
        
        self.validation_label = tk.Label(main_container, text="", 
                                        font=('Arial', 11), bg='white', fg='red')
        self.validation_label.pack(pady=(10, 0))
        
        button_section = tk.Frame(main_container, bg='white')
        button_section.pack(fill='x', pady=15)
        
        center_container = tk.Frame(button_section, bg='white')
        center_container.pack(expand=True)
        
        # Changed button text to include email - REMOVED
        save_btn = tk.Button(center_container, text="📚 ISSUE BOOK", 
                            font=('Arial', 12, 'bold'), bg='#27ae60', fg='white',
                            width=25, height=2, bd=0, 
                            command=self.save_book_issue_with_spinner)
        save_btn.pack(side='left', padx=10)
        
        clear_btn = tk.Button(center_container, text="🗑️ CLEAR FORM", 
                             font=('Arial', 12), bg='#95a5a6', fg='white',
                             width=15, height=2, bd=0,
                             command=self.clear_issue_form)
        clear_btn.pack(side='left', padx=10)
        
        instructions_frame = tk.Frame(main_container, bg='#fffde7', relief='solid', bd=1)
        instructions_frame.pack(fill='x', pady=(10, 5))
        
        # Updated instructions to include SMART BOOK SEARCH
        tk.Label(instructions_frame, 
                text="💡 Instructions:\n1. Fill all required fields (*)\n2. Type book title for SMART BOOK SEARCH\n3. Dropdown shows availability: ✅ Green = Available, 🔶 Orange = Low Stock, ⚠️ Red = Out of Stock\n4. Select from dropdown to auto-fill form\n5. Dates are automatically set\n6. Click SAVE to issue book and auto-save to SQLite3 with loading spinner\n7. ⚡ Performance: Optimized with caching",
                font=('Arial', 10), bg='#fffde7', fg='#555', justify='left').pack(padx=15, pady=10)
        
        def focus_next_widget(event):
            event.widget.tk_focusNext().focus()
            return "break"
        
        self.student_name_entry.bind('<Return>', lambda e: self.phone_entry.focus())
        #self.email_entry.bind('<Return>', lambda e: self.phone_entry.focus()) - REMOVED
        self.phone_entry.bind('<Return>', lambda e: self.book_name_entry.focus())
        self.book_name_entry.bind('<Return>', lambda e: self.book_author_entry.focus())
        self.book_author_entry.bind('<Return>', lambda e: self.isbn_code_entry.focus())
        self.isbn_code_entry.bind('<Return>', lambda e: self.save_book_issue_with_spinner())
        
        self.student_name_entry.focus()
        
        self.clock_running = True
        self.update_clock()
    
    def save_book_issue_with_spinner(self):
        """Save book issue with loading spinner"""
        # First validate
        student_name = self.student_name_var.get().strip()
        #email = self.email_var.get().strip() - REMOVED
        phone = self.phone_var.get().strip()
        book_name = self.book_name_var.get().strip()
        book_author = self.book_author_var.get().strip()
        isbn_code = self.isbn_code_var.get().strip()
        
        self.validation_label.config(text="")
        
        validation_errors = []
        
        if not student_name:
            validation_errors.append("Student Name")
        
        #if not email:
        #    validation_errors.append("Email Address")
        #elif '@' not in email or '.' not in email:
        #    self.validation_label.config(text="❌ Please enter valid email address (must contain @ and .)")
        #    self.email_entry.focus()
        #    return
        
        if not book_name:
            validation_errors.append("Book Title")
        
        if not book_author:
            validation_errors.append("Author")
        
        if not isbn_code:
            validation_errors.append("ISBN")
        
        if validation_errors:
            error_text = "❌ Please fill in required fields: " + ", ".join(validation_errors)
            self.validation_label.config(text=error_text)
            
            if not student_name:
                self.student_name_entry.focus()
            #elif not email:
            #    self.email_entry.focus()
            elif not book_name:
                self.book_name_entry.focus()
            elif not book_author:
                self.book_author_entry.focus()
            elif not isbn_code:
                self.isbn_code_entry.focus()
            return
        
        # Show loading spinner
        self.loading_spinner.show("Saving book issue to database...")
        
        # Run save in background thread to keep UI responsive
        threading.Thread(target=self._save_book_issue_thread, 
                        args=(student_name, "", phone, book_name, book_author, isbn_code),
                        daemon=True).start()
    
    def _save_book_issue_thread(self, student_name, email, phone, book_name, book_author, isbn_code):
        """Thread for saving book issue (runs in background)"""
        try:
            # Call the actual save function
            self._perform_book_issue_save(student_name, "", phone, book_name, book_author, isbn_code)
            
            # Update UI on main thread
            self.root.after(0, self._save_book_issue_complete)
        except Exception as e:
            # Handle error on main thread
            self.root.after(0, lambda: self._save_book_issue_error(str(e)))
    
    def _perform_book_issue_save(self, student_name, email, phone, book_name, book_author, isbn_code):
        """Perform the actual book issue save"""
        current_datetime = datetime.now()
        issue_date_str = current_datetime.strftime("%Y-%m-%d %I:%M:%S %p")
        due_date_obj = current_datetime + timedelta(days=14)
        due_date_str = due_date_obj.strftime("%Y-%m-%d")
        
        # Use fast lookup for book
        existing_book = self.data.book_lookup.get_by_isbn(isbn_code)
        if not existing_book:
            # Try by title as fallback
            existing_book = self.data.book_lookup.get_by_title(book_name)
        
        # OUT-OF-STOCK PROTECTION: Check if book is available
        if existing_book and existing_book['available_copies'] <= 0:
            raise Exception(f"'{book_name}' is currently OUT OF STOCK.\n\nAvailable copies: 0\nCannot issue this book.")
        
        existing_member = None
        for member in self.data.members:
            if member["name"].lower() == student_name.lower():
                existing_member = member
                break
        
        if not existing_member:
            new_member_id = f"M{len(self.data.members) + 1:04d}"
            new_member = {
                "id": new_member_id,
                "name": student_name,
                #"email": email, - REMOVED
                "phone": phone,
                "address": "",
                "membership_type": "Student",
                "membership_date": current_datetime.strftime("%Y-%m-%d"),
                "max_books": 5,
                "active": True,
                "total_borrowed": 0,
                "current_borrowed": 0,
                "join_date": current_datetime.strftime("%Y-%m-%d")
            }
            self.data.members.append(new_member)
            member_id = new_member_id
            existing_member = new_member
        else:
            member_id = existing_member["id"]
            if phone and not existing_member["phone"]:
                existing_member["phone"] = phone
            #if email and not existing_member["email"]: - REMOVED
            #    existing_member["email"] = email
        
        if not existing_book:
            new_book_id = len(self.data.books) + 1
            new_book = {
                "id": new_book_id,
                "s.no_code": f"T{new_book_id}",
                "title": book_name,
                "author": book_author,
                "isbn": isbn_code,
                "category": "General",
                "publisher": "",
                "publication_year": str(current_datetime.year),
                "page_count": 0,
                "price": 0,
                "total_copies": 1,
                "available_copies": 0,
                "shelf_location": "",
                "description": f"Manually added on {current_datetime.strftime('%Y-%m-%d')}",
                "added_date": current_datetime.strftime("%Y-%m-%d")
            }
            self.data.books.append(new_book)
            book_id = new_book_id
            existing_book = new_book
        else:
            book_id = existing_book["id"]
            if existing_book["available_copies"] > 0:
                existing_book["available_copies"] -= 1
                # Notify observers of stock change
                self.book_observable.notify_data_change('BOOK_STOCK_UPDATED', book_id, {
                    'old_stock': existing_book['available_copies'] + 1,
                    'new_stock': existing_book['available_copies'],
                    'book_title': existing_book['title'],
                    'book_author': existing_book['author']
                })
        
        transaction_id = len(self.data.transactions) + 1
        transaction = {
            "id": transaction_id,
            "book_id": book_id,
            "member_id": member_id,
            "issue_date": current_datetime.strftime("%Y-%m-%d"),
            "due_date": due_date_str,
            "return_date": "",
            "status": "issued",
            "fine_amount": 0,
            "fine_paid": False,
            "renewals": 0,
            "manual_entry": True,
            "student_name": student_name,
            "student_phone": phone,
            #"student_email": email, - REMOVED
            "book_title": book_name,
            "book_author": book_author,
            "book_isbn": isbn_code,
            "issue_timestamp": current_datetime.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if existing_member:
            existing_member["current_borrowed"] += 1
            existing_member["total_borrowed"] += 1
        
        self.data.transactions.append(transaction)
        
        self.history_manager.add_to_history(transaction_id, book_id, member_id, "issued")
        
        # Save to admin panel WITH EMAIL - REMOVED
        admin_save_id = self.admin_saver.save_transaction_to_admin(
            transaction, student_name, phone, "", book_name, book_author, isbn_code
        )
        
        # Clear cache
        self.data.book_cache.clear()
        self.data.book_lookup.build_index(self.data.books)
        
        self.data.save_data()
        self.history_manager.save_history()
        
        # Store success message for display
        self._last_success_message = f"""
        ✅ BOOK ISSUED SUCCESSFULLY!
        
        📋 TRANSACTION DETAILS:
        ──────────────────────────────
        👤 Student Name: {student_name}
        � Phone No.: {phone if phone else 'Not provided'}
        📚 Book Title: {book_name}
        ✍️ Author: {book_author}
        #️⃣ ISBN: {isbn_code}
        📅 Issue Date: {issue_date_str}
        ⏰ Due Date: {due_date_str}
        🔢 Transaction ID: {transaction_id}
        💾 SQLite3 Save ID: {admin_save_id}
        
        📥 Data automatically saved to SQLite3 database!
        🔄 UI automatically refreshed via real-time sync!
        ⚡ Performance: Optimized with caching
        No manual refresh needed - view in Admin Panel > View Reports
        """
    
    def _save_book_issue_complete(self):
        """Handle completion of book issue save"""
        self.loading_spinner.hide()
        
        # Show success message
        if hasattr(self, '_last_success_message'):
            messagebox.showinfo("SUCCESS", self._last_success_message)
            delattr(self, '_last_success_message')
        
        self.validation_label.config(text="✅ Book issued successfully! Auto-saved to SQLite3 database. UI refreshed automatically.", fg='green')
        
        self.root.after(2000, self.clear_issue_form)
        
        debug_sqlite_connection()
    
    def _save_book_issue_error(self, error_message):
        """Handle error during book issue save"""
        self.loading_spinner.hide()
        
        error_msg = f"❌ Database Error: {error_message}"
        self.validation_label.config(text=error_msg, fg='red')
        messagebox.showerror("ERROR", f"Failed to save to database:\n\n{error_message}")
    
    def update_clock(self):
        """Update the real-time clock display"""
        if not self.clock_running:
            return
            
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            if hasattr(self, 'current_time_label') and self.current_time_label.winfo_exists():
                self.current_time_label.config(text=current_time)
            
            if hasattr(self, 'issue_date_label') and self.issue_date_label.winfo_exists():
                issue_time = datetime.now().strftime("%Y-%m-%d")
                self.issue_date_label.config(text=issue_time)
                
                due_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
                if hasattr(self, 'due_date_label') and self.due_date_label.winfo_exists():
                    self.due_date_label.config(text=due_date)
            
            if self.clock_running:
                self.root.after(1000, self.update_clock)
        except:
            self.clock_running = False
    
    def save_book_issue(self):
        """Legacy function - now uses spinner version"""
        self.save_book_issue_with_spinner()
    
    def clear_issue_form(self):
        """Clear all form fields including email"""
        self.student_name_var.set("")
        self.email_var.set("")  # NEW: Clear email
        self.phone_var.set("")
        self.book_name_var.set("")
        self.book_author_var.set("")
        self.isbn_code_var.set("")
        
        self.validation_label.config(text="")
        self.student_name_entry.focus()

    # ==================== ADMIN SYSTEM ====================
    def create_admin_login_screen(self):
        """Admin login screen"""
        for widget in self.root.winfo_children():
            widget.destroy()
            
        bg_path = "login_bg.jpg"
        self.set_background(bg_path)
        
        panel_w, panel_h = 800, 500
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path)
        
        glass.add_text(panel_w//2, 40, "🔐 Admin Authentication",  
                       ('Arial', 24, 'bold'), color='white')
        
        glass.add_text(panel_w//2, 85, "Enter admin password to access management panel",
                       ('Arial', 14), color='#c7d5e0')
        
        input_frame = tk.Frame(glass, bg='gray20')
        input_frame.place(relx=0.5, rely=0.5, anchor='center', width=400, height=200)
        
        tk.Label(input_frame, text="Admin Password:",  
                 font=('Arial', 16), bg='gray20', fg='white').pack(pady=20)
        
        self.password_entry = tk.Entry(input_frame, font=('Arial', 16),  
                                       width=25, show="*", justify='center')
        self.password_entry.pack(pady=10)
        self.password_entry.focus()
        
        show_password_frame = tk.Frame(input_frame, bg='gray20')
        show_password_frame.pack(pady=10)
        
        self.show_password_var = tk.BooleanVar()
        show_password_cb = tk.Checkbutton(show_password_frame, text="Show Password",  
                                          variable=self.show_password_var,
                                          command=self.toggle_password_visibility,
                                          font=('Arial', 11), bg='gray20', fg='white',
                                          selectcolor='gray20')
        show_password_cb.pack()
        
        login_btn = tk.Button(input_frame, text="Login",  
                              font=('Arial', 14, 'bold'),  
                              bg='#3498db', fg='white',
                              command=self.verify_admin_password,
                              width=15, pady=8)
        login_btn.pack(pady=20)
        
        back_btn = tk.Button(glass, text="← Back to Main Menu",  
                            font=('Arial', 12), bg='#6c757d', fg='white',  
                            command=self.create_welcome_screen)
        glass.create_window(panel_w//2, panel_h-50, window=back_btn, anchor='center')
        
        self.password_entry.bind('<Return>', lambda event: self.verify_admin_password())
    
    def toggle_password_visibility(self):
        """Toggle password visibility"""
        if self.show_password_var.get():
            self.password_entry.config(show="")
        else:
            self.password_entry.config(show="*")
    
    def verify_admin_password(self):
        """Verify regular admin password"""
        entered_password = self.password_entry.get().strip()
        
        if not entered_password:
            messagebox.showerror("Error", "Please enter the admin password")
            return
        
        if entered_password == self.admin_password:
            self.create_admin_screen()
        else:
            messagebox.showerror("Access Denied",  
                                 "❌ Incorrect password! Please try again.")
            self.password_entry.delete(0, tk.END)
            self.password_entry.focus()
    
    def create_admin_screen(self):
        """Main admin panel - UPDATED WITH 7 CLEAN BUTTONS"""
        self.data.load_data()
        
        for widget in self.root.winfo_children():
            widget.destroy()
        
        bg_path = "login_bg.jpg"
        self.set_background(bg_path)
            
        panel_w, panel_h = 1000, 750
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path, radius=15)
        
        glass.add_text(panel_w//2, 35, "👨‍💼 Admin Panel - Library Management",  
                       ('Arial', 20, 'bold'), color='white')
        
        stats_frame = tk.Frame(glass, bg='gray20', relief='raised', bd=2)
        stats_label = tk.Label(stats_frame, text="📊 LIBRARY STATISTICS (SQLite3 Database)",  
                              font=('Arial', 14, 'bold'), bg='gray20', fg='white')
        stats_label.pack(pady=10)

        stats = self.book_manager.get_statistics()
        
        total_admin_saves = stats['admin_saves']
        today_admin_saves = stats['today_admin_saves']
        active_borrowers_sqlite = stats['active_borrowers_sqlite']
        
        stats_text = f"Total Books: {stats['total_books']} | Available Copies: {stats['available_copies']} | Active Members: {stats['active_members']} | Active Borrowings: {stats['active_borrowings']} | SQLite3 Active Borrowers: {active_borrowers_sqlite} | SQLite3 Saves: {total_admin_saves} (Today: {today_admin_saves}) |  Real-time Sync: ACTIVE | ⏳ Loading Spinner: READY | ⚡ Performance: OPTIMIZED"
        stats_details = tk.Label(stats_frame, text=stats_text,  
                                 font=('Arial', 12), bg='gray20', fg='#adb5bd')
        stats_details.pack(pady=8, padx=20)
        
        glass.create_window(panel_w//2, 140, window=stats_frame, anchor='center', width=panel_w - 40)

        button_frame = tk.Frame(glass, bg='gray20')
        
        # ✅ MODIFIED: REMOVED "⚠️ Out of Stock Restock" button as requested
        buttons = [
            ("📚 Manage Books", self.manage_books, '#3498db'),                     # CRITICAL: All book operations + Excel
            ("👥 Active Borrowers", self.admin_active_borrowers, '#3498db'),       # CRITICAL: Current loans + returns (shows overdue)
            ("💾 View SQLite3 Saves", self.view_sqlite_saves, '#27ae60'),         # IMPORTANT: Reports + database (includes history)
            (" Change Password", self.change_admin_password, '#8e44ad'),        # NECESSARY: Security
            ("← Back to Main", self.create_welcome_screen, '#6c757d')             # NECESSARY: Navigation
        ]
        
        for idx, (text, command, color) in enumerate(buttons):
            btn = tk.Button(button_frame, text=text, font=('Arial', 12),  
                            bg=color, fg='white', width=25,
                            command=command, bd=0, pady=10)
            row = idx // 3
            col = idx % 3
            btn.grid(row=row, column=col, padx=10, pady=10, sticky='ew')

        glass.create_window(panel_w//2, 450, window=button_frame, anchor='center', width=panel_w - 40)
    
    # ==================== MANAGE BOOKS WITH EXCEL INTEGRATION ====================
    def manage_books(self):
        """Manage books interface with Excel integration"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        bg_path = "voting_bg.jpg"
        
        panel_w, panel_h = 1200, 700
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path, radius=15)
        
        glass.add_text(panel_w//2, 40, "📚 Manage Books - Excel Integration",  
                      ('Arial', 24, 'bold'), color='white')
        
        # Excel info frame
        excel_info = tk.Frame(glass, bg='#34495e', relief='raised', bd=2)
        excel_info.place(relx=0.5, y=100, anchor='center', width=panel_w-100, height=60)
        
        excel_text = f"📊 EXCEL FILE: Department_library_books.xlsx | 📋 TOTAL BOOKS IN DATABASE: {len(self.data.books)} | 🔄 Real-time Sync: ACTIVE | ⏳ Loading Spinner: READY | ⚡ Performance: OPTIMIZED"
        excel_label = tk.Label(excel_info, text=excel_text,  
                              font=('Arial', 12, 'bold'), bg='#34495e', fg='white')
        excel_label.pack(pady=15)
        
        # Books treeview with MULTI-SELECTION
        tree_frame = tk.Frame(glass, bg='#2c3e50', relief='raised', bd=2)
        tree_frame.place(relx=0.5, y=200, anchor='center', width=panel_w-100, height=400)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        self.books_tree = ttk.Treeview(tree_frame, 
                                      columns=("S.no", "Authour Title", "Book title", "Publisher", "Page count", "Price", "Available", "Total", "ISBN"),
                                      show='headings',
                                      yscrollcommand=v_scrollbar.set,
                                      xscrollcommand=h_scrollbar.set,
                                      selectmode='extended'  # Changed to allow multiple selection
        )
        
        # Configure column widths - WIDER for better visibility
        self.books_tree.heading("S.no", text="S.no")
        self.books_tree.column("S.no", width=80, minwidth=60, stretch=False)
        
        self.books_tree.heading("Authour Title", text="Authour Title")
        self.books_tree.column("Authour Title", width=250, minwidth=200, stretch=True)
        
        self.books_tree.heading("Book title", text="Book title")
        self.books_tree.column("Book title", width=300, minwidth=250, stretch=True)
        
        self.books_tree.heading("Publisher", text="Publisher")
        self.books_tree.column("Publisher", width=200, minwidth=150, stretch=True)
        
        self.books_tree.heading("Page count", text="Page count")
        self.books_tree.column("Page count", width=100, minwidth=80, stretch=False)
        
        self.books_tree.heading("Price", text="Price")
        self.books_tree.column("Price", width=120, minwidth=100, stretch=False)
        
        self.books_tree.heading("No ", text="No ")
        self.books_tree.column("No ", width=80, minwidth=60, stretch=False)
        
        self.books_tree.heading("Available", text="Available")
        self.books_tree.column("Available", width=100, minwidth=80, stretch=False)
        
        self.books_tree.heading("Status", text="Status")
        self.books_tree.column("Status", width=120, minwidth=100, stretch=False)
        
        self.books_tree.heading("Select", text="Select")
        self.books_tree.column("Select", width=60, minwidth=50, stretch=False)
        
        # Configure scrollbars
        h_scrollbar.config(command=self.books_tree.xview)
        v_scrollbar.config(command=self.books_tree.yview)
         
        # Pack treeview
        self.books_tree.pack(side='left', fill='both', expand=True)
        
        # Load books data
        self.refresh_books_view()
        
        # Bind click and double-click events
        self.books_tree.bind('<Button-1>', self.on_tree_click)
        self.books_tree.bind('<Double-1>', self.on_row_double_click)
    
    def on_tree_click(self, event):
        """Toggle row selection on single click (no Ctrl required) and mark select column."""
        item = self.books_tree.identify_row(event.y)
        if not item:
            return

        # Toggle selection for clicked item
        currently_selected = list(self.books_tree.selection())
        if item in currently_selected:
            # remove selection
            self.books_tree.selection_remove(item)
            # update mark
            values = list(self.books_tree.item(item, 'values'))
            if len(values) >= 10:
                values[9] = " "
                self.books_tree.item(item, values=values)
            # also remove from selected set if present
            try:
                s_no = self.books_tree.item(item, 'values')[0]
                book = self.book_manager.get_book_by_sno(s_no)
                if book and book['id'] in self.selected_books_for_delete:
                    self.selected_books_for_delete.remove(book['id'])
            except:
                pass
        else:
            # add selection
            self.books_tree.selection_add(item)
            values = list(self.books_tree.item(item, 'values'))
            if len(values) >= 10:
                values[9] = "✓"
                self.books_tree.item(item, values=values)
            try:
                s_no = self.books_tree.item(item, 'values')[0]
                book = self.book_manager.get_book_by_sno(s_no)
                if book:
                    self.selected_books_for_delete.add(book['id'])
            except:
                pass

    def on_row_double_click(self, event):
        """Open edit dialog for double-clicked row."""
        item = self.books_tree.identify_row(event.y)
        if not item:
            return
        # set selection to this item and open edit dialog
        self.books_tree.selection_set(item)
        self.edit_book_dialog()
    
    def refresh_books_view(self):
        """Refresh books treeview with actual data - FIXED to match Excel format"""
        if hasattr(self, 'books_tree'):
            # Clear existing items
            for item in self.books_tree.get_children():
                self.books_tree.delete(item)
        
        print(f"\n📊 DEBUG: Loading {len(self.data.books)} books from database...")
        
        if len(self.data.books) == 0:
            print("⚠️ No books found in database!")
            self.books_tree.insert('', 'end', values=(
                "No Data", "No books imported", "Please import from Excel first", 
                "", "", "", "", "", "", ""
            ))
            return
        
        # Load data from self.data.books
        books_added = 0
        for book in self.data.books:
            try:
                # Get values as stored in database
                s_no_val = book.get('s.no_code', '')
                author_val = book.get('author', 'Unknown Author')
                title_val = book.get('title', 'Unknown Title')
                publisher_val = book.get('publisher', '')
                page_count = book.get('page_count', 0)
                price = book.get('price', 0)
                total_copies = book.get('total_copies', 1)
                available_copies = book.get('available_copies', 0)
                
                # Format price like Excel (40NR, 95NR, etc.)
                price_display = f"{int(price)}NR"
                
                # Determine status
                if available_copies <= 0:
                    status = "❌ OUT OF STOCK"
                elif available_copies < total_copies:
                    status = f"⚠️ {total_copies - available_copies} issued"
                else:
                    status = "✅ Available"
                
                # Check if selected for delete
                select_mark = "✓" if book['id'] in self.selected_books_for_delete else " "
                
                self.books_tree.insert('', 'end', values=(
                    s_no_val,
                    author_val,
                    title_val,
                    publisher_val,
                    int(page_count),
                    price_display,
                    int(total_copies),
                    int(available_copies),
                    status,
                    select_mark
                ))
                books_added += 1
                
                # Update UI every 100 books to prevent freezing
                if books_added % 100 == 0:
                    self.root.update_idletasks()
                
                if books_added <= 3:  # Debug first 3 books
                    print(f"  Book {books_added}: S.no='{s_no_val}', Author='{author_val}', Title='{title_val}'")
                    
            except Exception as e:
                print(f"❌ Error loading book {books_added + 1}: {e}")
                continue
        
        # Final UI update
        self.root.update_idletasks()
        print(f"✅ Loaded {books_added} books into treeview")
    
    def create_excel_sync_tab(self, parent):
        """Create Excel sync instructions tab"""
        info_frame = tk.Frame(parent, bg='#f8f9fa', relief='solid', bd=1)
        info_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        instructions = """
        📊 EXCEL INTEGRATION INSTRUCTIONS:
        
        1. 📤 EXPORT TO EXCEL:
           • Click "Export to Excel" button
           • All books from database will be saved to:
             ➜ Department_library_books.xlsx
           • File will be created in same folder as app
        
        2. 📥 IMPORT FROM EXCEL:
           • Edit the Excel file (add/remove/update books)
           • Click "Import from Excel" button
           • All data from Excel will replace current database
           • ⚠️ Warning: This will overwrite existing data!
        
        3. 📋 EXCEL FORMAT (As per your Excel sheet):
           • Column A: S.no (e.g., 17, 15, 73)
           • Column B: Authour Title
           • Column C: Book title
           • Column D: Publisher
           • Column E: Page count
           • Column F: Price (e.g., 40NR, 95NR, 250NR)
           • Column G: No  (Available copies)
        
        4. ✏️ EDIT/DELETE BOOKS:
           • Click "Edit/Select for Delete" button
           • Single click on a book to edit it
           • Click the "Select" column to mark for deletion (✓)
           • Select multiple books by clicking their "Select" column
           • Click "Delete Selected" to delete all marked books
           • Click "Update" to refresh the view
        
        5. 🔄 AUTO-SYNC & REAL-TIME UPDATES:
           • When you issue/return books, "Available_Copies" updates
           • When you restock books, stock updates in real-time
           • UI automatically refreshes via observer pattern
           • No manual refresh needed
        
        6. 💾 BACKUP:
           • Excel file serves as backup
           • Keep Excel file safe
           • You can edit books directly in Excel
        
        7. ⏳ LOADING SPINNER:
           • Shows progress when saving to database
           • Prevents accidental double-clicks
           • Provides clear visual feedback
        
        8. ⚡ PERFORMANCE OPTIMIZATIONS:
           • Fast cache system for frequently accessed data
           • Hash-based lookups for O(1) book searches
           • Background threading for database operations
           • Memory-efficient data structures
        """
        
        tk.Label(info_frame, text=instructions, 
                font=('Arial', 11), bg='#f8f9fa', fg='#2c3e50',
                justify='left').pack(padx=20, pady=20)
        
        # Quick stats
        stats_frame = tk.Frame(info_frame, bg='#e8f4f8', relief='solid', bd=1)
        stats_frame.pack(fill='x', padx=20, pady=10)
        
        total_books = len(self.data.books)
        total_copies = sum(book.get('total_copies', 1) for book in self.data.books)
        available_copies = sum(book.get('available_copies', 0) for book in self.data.books)
        
        stats_text = f"📈 CURRENT STATS: Books: {total_books} | Total Copies: {total_copies} | Available: {available_copies} | Selected for Delete: {len(self.selected_books_for_delete)} | 🔄 Real-time Sync: ACTIVE | ⚡ Performance: OPTIMIZED"
        tk.Label(stats_frame, text=stats_text, 
                font=('Arial', 12, 'bold'), bg='#e8f4f8', fg='#2c3e50').pack(pady=10)
    
    def edit_or_select_book(self):
        """Edit single book or manage selection - combines both functions"""
        selection = self.books_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a book first")
            return
        
        item = self.books_tree.item(selection[0])
        values = item['values']
        s_no = values[0]
        
        # Check if clicked on select column
        for sel in selection:
            item_values = self.books_tree.item(sel, 'values')
            if len(item_values) > 9:
                s_no_val = item_values[0]
                book = self.book_manager.get_book_by_sno(s_no_val)
                if book:
                    if book['id'] in self.selected_books_for_delete:
                        self.selected_books_for_delete.remove(book['id'])
                        # Update display
                        new_values = list(item_values)
                        new_values[9] = " "
                        self.books_tree.item(sel, values=new_values)
                    else:
                        self.selected_books_for_delete.add(book['id'])
                        # Update display
                        new_values = list(item_values)
                        new_values[9] = "✓"
                        self.books_tree.item(sel, values=new_values)
        
        # If only one book selected and not in select mode, edit it
        if len(selection) == 1 and not values[9] == "✓":
            self.edit_book_dialog()
    
    def edit_book_dialog(self):
        """Edit selected book dialog"""
        selection = self.books_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a book to edit")
            return
        
        item = self.books_tree.item(selection[0])
        values = item['values']
        s_no = values[0]
        
        # Find the book in database
        book = self.book_manager.get_book_by_sno(s_no)
        if not book:
            messagebox.showerror("Error", f"Book with S.no {s_no} not found in database")
            return
        
        # Create edit dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Book: {book['title']}")
        dialog.geometry("500x550")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text=f"✏️ Edit Book: {book['title'][:50]}",  
                 font=('Arial', 16, 'bold'), bg='white', fg='#2c3e50').pack(pady=20)
        
        # Form fields
        fields_frame = tk.Frame(dialog, bg='white')
        fields_frame.pack(fill='both', expand=True, padx=30, pady=10)
        
        # S.no
        tk.Label(fields_frame, text="S.no *", font=('Arial', 11, 'bold'), 
                bg='white').grid(row=0, column=0, sticky='w', pady=5)
        sno_var = tk.StringVar(value=book.get('s.no_code', ''))
        sno_entry = tk.Entry(fields_frame, textvariable=sno_var, font=('Arial', 11), width=30)
        sno_entry.grid(row=0, column=1, pady=5, padx=10)
        
        # Authour Title
        tk.Label(fields_frame, text="Authour Title *", font=('Arial', 11, 'bold'),
                bg='white').grid(row=1, column=0, sticky='w', pady=5)
        author_var = tk.StringVar(value=book.get('author', ''))
        author_entry = tk.Entry(fields_frame, textvariable=author_var, font=('Arial', 11), width=30)
        author_entry.grid(row=1, column=1, pady=5, padx=10)
        
        # Book title
        tk.Label(fields_frame, text="Book title *", font=('Arial', 11, 'bold'),
                bg='white').grid(row=2, column=0, sticky='w', pady=5)
        title_var = tk.StringVar(value=book.get('title', ''))
        title_entry = tk.Entry(fields_frame, textvariable=title_var, font=('Arial', 11), width=30)
        title_entry.grid(row=2, column=1, pady=5, padx=10)
        
        # Publisher
        tk.Label(fields_frame, text="Publisher", font=('Arial', 11), 
                bg='white').grid(row=3, column=0, sticky='w', pady=5)
        publisher_var = tk.StringVar(value=book.get('publisher', ''))
        publisher_entry = tk.Entry(fields_frame, textvariable=publisher_var, font=('Arial', 11), width=30)
        publisher_entry.grid(row=3, column=1, pady=5, padx=10)
        
        # Page count
        tk.Label(fields_frame, text="Page count", font=('Arial', 11), 
                bg='white').grid(row=4, column=0, sticky='w', pady=5)
        pages_var = tk.StringVar(value=str(book.get('page_count', 0)))
        pages_entry = tk.Entry(fields_frame, textvariable=pages_var, font=('Arial', 11), width=30)
        pages_entry.grid(row=4, column=1, pady=5, padx=10)
        
        # Price
        tk.Label(fields_frame, text="Price (e.g., 400NR)", font=('Arial', 11), 
                bg='white').grid(row=5, column=0, sticky='w', pady=5)
        price_var = tk.StringVar(value=f"{int(book.get('price', 0))}NR")
        price_entry = tk.Entry(fields_frame, textvariable=price_var, font=('Arial', 11), width=30)
        price_entry.grid(row=5, column=1, pady=5, padx=10)
        
        # Total Copies
        tk.Label(fields_frame, text="Total Copies *", font=('Arial', 11, 'bold'), 
                bg='white').grid(row=6, column=0, sticky='w', pady=5)
        total_copies_var = tk.StringVar(value=str(book.get('total_copies', 1)))
        total_copies_entry = tk.Entry(fields_frame, textvariable=total_copies_var, font=('Arial', 11), width=30)
        total_copies_entry.grid(row=6, column=1, pady=5, padx=10)
        
        # Available Copies (Read-only, for info)
        tk.Label(fields_frame, text="Available Copies", font=('Arial', 11), 
                bg='white').grid(row=7, column=0, sticky='w', pady=5)
        available_copies_var = tk.StringVar(value=str(book.get('available_copies', 0)))
        available_copies_label = tk.Label(fields_frame, textvariable=available_copies_var, 
                                         font=('Arial', 11, 'bold'), bg='white', fg='#3498db')
        available_copies_label.grid(row=7, column=1, pady=5, padx=10, sticky='w')
        
        # Status
        tk.Label(fields_frame, text="Status", font=('Arial', 11), 
                bg='white').grid(row=8, column=0, sticky='w', pady=5)
        if book['available_copies'] <= 0:
            status_text = "❌ OUT OF STOCK"
            status_color = 'red'
        elif book['available_copies'] < book['total_copies']:
            issued = book['total_copies'] - book['available_copies']
            status_text = f"⚠️ {issued} copies issued"
            status_color = 'orange'
        else:
            status_text = "✅ All copies available"
            status_color = 'green'
        
        status_label = tk.Label(fields_frame, text=status_text, 
                               font=('Arial', 11, 'bold'), bg='white', fg=status_color)
        status_label.grid(row=8, column=1, pady=5, padx=10, sticky='w')
        
        def update_book():
            """Update book in database"""
            # Validate required fields
            if not sno_var.get().strip():
                messagebox.showerror("Error", "Please enter S.no")
                sno_entry.focus()
                return
            
            if not author_var.get().strip():
                messagebox.showerror("Error", "Please enter Authour Title")
                author_entry.focus()
                return
            
            if not title_var.get().strip():
                messagebox.showerror("Error", "Please enter Book title")
                title_entry.focus()
                return
            
            try:
                total_copies = int(total_copies_var.get())
                if total_copies < 1:
                    messagebox.showerror("Error", "Total copies must be at least 1")
                    total_copies_entry.focus()
                    return
                
                # Check if trying to reduce copies below currently issued copies
                currently_issued = book['total_copies'] - book['available_copies']
                if total_copies < currently_issued:
                    messagebox.showerror("Error", 
                                       f"Cannot reduce total copies below {currently_issued}\n"
                                       f"{currently_issued} copies are currently issued")
                    total_copies_entry.focus()
                    return
                    
            except ValueError:
                messagebox.showerror("Error", "Please enter valid number for total copies")
                total_copies_entry.focus()
                return
            
            # Process price
            price_str = price_var.get().strip().upper()
            try:
                if 'NR' in price_str:
                    price_value = float(price_str.replace('NR', '').strip())
                elif 'INR' in price_str:
                    price_value = float(price_str.replace('INR', '').strip())
                elif 'HR' in price_str:
                    price_value = float(price_str.replace('HR', '').strip())
                elif 'MIR' in price_str:
                    price_value = float(price_str.replace('MIR', '').strip())
                elif 'USD' in price_str:
                    price_value = float(price_str.replace('USD', '').strip()) * 75
                else:
                    price_value = float(price_str)
            except:
                price_value = book.get('price', 0)
            
            # Prepare updated data
            updated_data = {
                "s.no_code": sno_var.get().strip(),
                "author": author_var.get().strip(),
                "title": title_var.get().strip(),
                "publisher": publisher_var.get().strip(),
                "page_count": int(pages_var.get()) if pages_var.get().strip() else 0,
                "price": price_value,
                "total_copies": total_copies
            }
            
            # Show loading spinner
            self.loading_spinner.show(f"Updating '{book['title']}'...")
            self.root.update()
            
            try:
                # Update the book
                success = self.book_manager.update_book(book['id'], updated_data)
                
                if success:
                    # Clear cache
                    self.data.book_cache.clear()
                    
                    # Notify observers of the change
                    self.book_observable.notify_data_change('BOOK_STOCK_UPDATED', book['id'], {
                        'book_title': book['title'],
                        'book_author': book['author'],
                        'new_total': total_copies
                    })
                    
                    # Hide spinner
                    self.loading_spinner.hide()
                    
                    messagebox.showinfo("Success", 
                                      f"✅ Book updated successfully!\n\n"
                                      f"S.no: {sno_var.get()}\n"
                                      f"Title: {title_var.get()}\n"
                                      f"Author: {author_var.get()}\n"
                                      f"Total Copies: {total_copies}\n"
                                      f"Available: {book['available_copies']}\n\n"
                                      f"🔄 UI will refresh automatically via real-time sync\n"
                                      f"⚡ Performance: Optimized with caching")
                    
                    # Refresh view
                    self.refresh_books_view()
                    dialog.destroy()
                else:
                    self.loading_spinner.hide()
                    messagebox.showerror("Error", "Failed to update book")
            except Exception as e:
                self.loading_spinner.hide()
                messagebox.showerror("Error", f"Failed to save to database:\n\n{str(e)}")
        
        # Buttons
        button_frame = tk.Frame(dialog, bg='white')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Update Book", font=('Arial', 12),  
                  bg='#27ae60', fg='white', command=update_book).pack(side='left', padx=5)
        tk.Button(button_frame, text="Cancel", font=('Arial', 12),  
                  bg='#95a5a6', fg='white', command=dialog.destroy).pack(side='left', padx=5)
    
    def delete_selected_books(self):
        """Delete selected books from tree selection"""
        selection = self.books_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select books to delete")
            return
        
        # Get book ids from selected rows
        book_ids = []
        for sel in selection:
            item = self.books_tree.item(sel)
            values = item['values']
            s_no = values[0]
            book = self.book_manager.get_book_by_sno(s_no)
            if book:
                book_ids.append(book['id'])
        
        if not book_ids:
            messagebox.showerror("Error", "Could not find books for selected rows")
            return
        
        # Confirm deletion
        selected_count = len(book_ids)
        if not messagebox.askyesno("Confirm Delete", 
                                  f"Are you sure you want to delete {selected_count} selected books?\n\n"
                                  f"This action cannot be undone!"):
            return
        
        # Show loading spinner
        self.loading_spinner.show(f"Deleting {selected_count} books...")
        self.root.update()
        
        try:
            # Delete selected books
            success = self.book_manager.delete_selected_books(book_ids)
            
            if success:
                # Clear cache
                self.data.book_cache.clear()
                
                # Rebuild lookup index
                self.data.book_lookup.build_index(self.data.books)
                
                # Notify observers of deletions
                for book_id in book_ids:
                    self.book_observable.notify_data_change('BOOK_DELETED', book_id)
                
                # Clear selection
                self.selected_books_for_delete.clear()
                
                # Hide spinner
                self.loading_spinner.hide()
                
                # Refresh view
                self.refresh_books_view()
            else:
                self.loading_spinner.hide()
        except Exception as e:
            self.loading_spinner.hide()
            messagebox.showerror("Error", f"Failed to delete books:\n\n{str(e)}")
    
    def export_to_excel_with_spinner(self):
        """Export books to Excel with loading spinner"""
        # Show loading spinner
        self.loading_spinner.show("Exporting to Excel...")
        self.root.update()
        
        # Run in background thread
        threading.Thread(target=self._export_to_excel_thread, daemon=True).start()
    
    def _export_to_excel_thread(self):
        """Thread for exporting to Excel"""
        try:
            success = self.excel_manager.export_to_excel()
            
            # Update UI on main thread
            if success:
                self.root.after(0, lambda: self._export_to_excel_complete())
            else:
                self.root.after(0, lambda: self._export_to_excel_error())
        except Exception as e:
            self.root.after(0, lambda: self._export_to_excel_error(str(e)))
    
    def _export_to_excel_complete(self):
        """Handle successful export"""
        self.loading_spinner.hide()
        messagebox.showinfo("Success", 
                          f"✅ All books exported to Excel successfully!\n\n"
                          f"File: Department_library_books.xlsx\n"
                          f"Books exported: {len(self.data.books)}\n\n"
                          f"Format: Excel sheet format (S.no, Authour Title, Book title, Publisher, Page count, Price, No )\n"
                          f"⚡ Performance: Optimized export")
    
    def _export_to_excel_error(self, error_msg=None):
        """Handle export error"""
        self.loading_spinner.hide()
        if error_msg:
            messagebox.showerror("Error", 
                               f"❌ Failed to export to Excel:\n\n{error_msg}")
        else:
            messagebox.showerror("Error", 
                               "❌ Failed to export to Excel.\n"
                               "Make sure Excel file is not open in another program.")
    
    def export_to_excel(self):
        """Legacy function - now uses spinner version"""
        self.export_to_excel_with_spinner()
    
    def import_from_excel_with_spinner(self):
        """Import books from Excel with loading spinner"""
        if not messagebox.askyesno("Confirm Import", 
                                  "⚠️ WARNING: This will replace ALL current books with Excel data!\n\n"
                                  "• Current books will be deleted\n"
                                  "• Excel data will replace everything\n"
                                  "• This action cannot be undone!\n\n"
                                  "Do you want to continue?"):
            return
        
        # Show loading spinner
        self.loading_spinner.show("Importing from Excel...")
        self.root.update()
        
        # Run in background thread
        threading.Thread(target=self._import_from_excel_thread, daemon=True).start()
    
    def _import_from_excel_thread(self):
        """Thread for importing from Excel"""
        try:
            success = self.excel_manager.import_from_excel()
            
            # Update UI on main thread
            if success:
                self.root.after(0, lambda: self._import_from_excel_complete())
            else:
                self.root.after(0, lambda: self._import_from_excel_error())
        except Exception as e:
            self.root.after(0, lambda: self._import_from_excel_error(str(e)))
    
    def _import_from_excel_complete(self):
        """Handle successful import"""
        self.loading_spinner.hide()
        
        # Clear cache
        self.data.book_cache.clear()
        self.data.book_lookup.build_index(self.data.books)
        
        # Notify observers of bulk import
        for book in self.data.books:
            self.book_observable.notify_data_change('BOOK_IMPORTED', book['id'])
        
        # Clear selection
        self.selected_books_for_delete.clear()
        # Refresh view
        self.refresh_books_view()
        
        messagebox.showinfo("Success", 
                          f"✅ Books imported from Excel successfully!\n\n"
                          f"Books imported: {len(self.data.books)}\n"
                          f"File: Department_library_books.xlsx\n"
                          f"Format: Excel sheet format imported and converted\n"
                          f"⚡ Performance: Optimized import with caching")
    
    def _import_from_excel_error(self, error_msg=None):
        """Handle import error"""
        self.loading_spinner.hide()
        if error_msg:
            messagebox.showerror("Error", 
                               f"❌ Failed to import from Excel:\n\n{error_msg}")
        else:
            messagebox.showerror("Error", 
                               "❌ Failed to import from Excel.\n"
                               "Make sure:\n"
                               "1. Excel file exists\n"
                               "2. File has correct Excel sheet format\n"
                               "3. File is not corrupted")
    
    def import_from_excel(self):
        """Legacy function - now uses spinner version"""
        self.import_from_excel_with_spinner()
    
    def add_new_book_dialog(self):
        """Dialog to add new book in Excel sheet format"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Book (Excel Sheet Format)")
        dialog.geometry("500x500")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="➕ Add New Book (Excel Sheet Format)",  
                 font=('Arial', 16, 'bold'), bg='white', fg='#2c3e50').pack(pady=20)
        
        # Form fields in Excel sheet format
        fields_frame = tk.Frame(dialog, bg='white')
        fields_frame.pack(fill='both', expand=True, padx=30, pady=10)
        
        # S.no (Excel Column A)
        tk.Label(fields_frame, text="S.no *", font=('Arial', 11, 'bold'), 
                bg='white').grid(row=0, column=0, sticky='w', pady=5)
        sno_var = tk.StringVar(value=f"{len(self.data.books) + 1}")
        sno_entry = tk.Entry(fields_frame, textvariable=sno_var, font=('Arial', 11), width=30)
        sno_entry.grid(row=0, column=1, pady=5, padx=10)
        
        # Authour Title (Excel Column B)
        tk.Label(fields_frame, text="Authour Title *", font=('Arial', 11, 'bold'),
                bg='white').grid(row=1, column=0, sticky='w', pady=5)
        author_var = tk.StringVar()
        author_entry = tk.Entry(fields_frame, textvariable=author_var, font=('Arial', 11), width=30)
        author_entry.grid(row=1, column=1, pady=5, padx=10)
        
        # Book title (Excel Column C)
        tk.Label(fields_frame, text="Book title *", font=('Arial', 11, 'bold'),
                bg='white').grid(row=2, column=0, sticky='w', pady=5)
        title_var = tk.StringVar()
        title_entry = tk.Entry(fields_frame, textvariable=title_var, font=('Arial', 11), width=30)
        title_entry.grid(row=2, column=1, pady=5, padx=10)
        
        # Publisher (Excel Column D)
        tk.Label(fields_frame, text="Publisher", font=('Arial', 11), 
                bg='white').grid(row=3, column=0, sticky='w', pady=5)
        publisher_var = tk.StringVar()
        publisher_entry = tk.Entry(fields_frame, textvariable=publisher_var, font=('Arial', 11), width=30)
        publisher_entry.grid(row=3, column=1, pady=5, padx=10)
        
        # Page count (Excel Column E)
        tk.Label(fields_frame, text="Page count", font=('Arial', 11), 
                bg='white').grid(row=4, column=0, sticky='w', pady=5)
        pages_var = tk.StringVar(value="300")
        pages_entry = tk.Entry(fields_frame, textvariable=pages_var, font=('Arial', 11), width=30)
        pages_entry.grid(row=4, column=1, pady=5, padx=10)
        
        # Price (Excel Column F)
        tk.Label(fields_frame, text="Price (e.g., 400NR)", font=('Arial', 11), 
                bg='white').grid(row=5, column=0, sticky='w', pady=5)
        price_var = tk.StringVar(value="500NR")
        price_entry = tk.Entry(fields_frame, textvariable=price_var, font=('Arial', 11), width=30)
        price_entry.grid(row=5, column=1, pady=5, padx=10)
        
        # No  (Available copies) (Excel Column G)
        tk.Label(fields_frame, text="No  (Copies) *", font=('Arial', 11, 'bold'), 
                bg='white').grid(row=6, column=0, sticky='w', pady=5)
        copies_var = tk.StringVar(value="1")
        copies_entry = tk.Entry(fields_frame, textvariable=copies_var, font=('Arial', 11), width=30)
        copies_entry.grid(row=6, column=1, pady=5, padx=10)
        
        def save_book():
            """Save new book to database in Excel sheet format"""
            # Validate required fields
            if not sno_var.get().strip():
                messagebox.showerror("Error", "Please enter S.no")
                sno_entry.focus()
                return
            
            if not author_var.get().strip():
                messagebox.showerror("Error", "Please enter Authour Title")
                author_entry.focus()
                return
            
            if not title_var.get().strip():
                messagebox.showerror("Error", "Please enter Book title")
                title_entry.focus()
                return
            
            try:
                copies = int(copies_var.get())
                if copies < 1:
                    messagebox.showerror("Error", "Copies must be at least 1")
                    copies_entry.focus()
                    return
            except:
                messagebox.showerror("Error", "Please enter valid number for copies")
                copies_entry.focus()
                return
            
            # Process price (handle currency codes)
            price_str = price_var.get().strip().upper()
            price_value = 0
            try:
                if 'NR' in price_str:
                    price_value = float(price_str.replace('NR', '').strip())
                elif 'INR' in price_str:
                    price_value = float(price_str.replace('INR', '').strip())
                elif 'HR' in price_str:
                    price_value = float(price_str.replace('HR', '').strip())
                elif 'MIR' in price_str:
                    price_value = float(price_str.replace('MIR', '').strip())
                elif 'USD' in price_str:
                    price_value = float(price_str.replace('USD', '').strip()) * 75
                else:
                    price_value = float(price_str)
            except:
                price_value = 500
            
            # Show loading spinner
            self.loading_spinner.show(f"Saving '{title_var.get()}' to database...")
            self.root.update()
            
            try:
                # Create book data (convert to database format)
                book_data = {
                    "s.no_code": sno_var.get().strip(),  # Add s.no_code
                    "title": title_var.get().strip(),  # Book title
                    "author": author_var.get().strip(),  # Authour Title
                    "isbn": f"ISBN{len(self.data.books) + 1:04d}",
                    "category": "General",
                    "publisher": publisher_var.get().strip(),
                    "publication_year": str(datetime.now().year),
                    "page_count": int(pages_var.get()) if pages_var.get().strip() else 0,
                    "price": price_value,
                    "total_copies": copies,
                    "available_copies": copies,
                    "shelf_location": "A1",
                    "description": f"Added on {datetime.now().strftime('%Y-%m-%d')}"
                }
                
                # Add book
                book_id = self.book_manager.add_book(book_data)
                
                # Clear cache
                self.data.book_cache.clear()
                
                # Rebuild lookup index
                self.data.book_lookup.build_index(self.data.books)
                
                # Notify observers of new book
                self.book_observable.notify_data_change('BOOK_ADDED', book_id, {
                    'book_title': title_var.get().strip(),
                    'book_author': author_var.get().strip()
                })
                
                # Hide spinner
                self.loading_spinner.hide()
                
                messagebox.showinfo("Success", 
                                  f"✅ Book added successfully!\n\n"
                                  f"S.no: {sno_var.get()}\n"
                                  f"Authour Title: {author_var.get()}\n"
                                  f"Book title: {title_var.get()}\n"
                                  f"Publisher: {publisher_var.get()}\n"
                                  f"Price: {price_var.get()}\n"
                                  f"Copies: {copies}\n"
                                  f"Book ID: {book_id}\n\n"
                                  f"🔄 UI will refresh automatically via real-time sync\n"
                                  f"⚡ Performance: Optimized with caching")
                
                # Refresh books view
                self.refresh_books_view()
                
                dialog.destroy()
            except Exception as e:
                self.loading_spinner.hide()
                messagebox.showerror("Error", f"Failed to save to database:\n\n{str(e)}")
        
        # Buttons
        button_frame = tk.Frame(dialog, bg='white')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Save Book", font=('Arial', 12),  
                  bg='#27ae60', fg='white', command=save_book).pack(side='left', padx=5)
        tk.Button(button_frame, text="Cancel", font=('Arial', 12),  
                  bg='#95a5a6', fg='white', command=dialog.destroy).pack(side='left', padx=5)
        
        author_entry.focus()
    
    def view_sqlite_saves(self):
        """View SQLite3 database saves with email data"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        bg_path = "voting_bg.jpg"
        self.set_background(bg_path)
        
        panel_w, panel_h = 1200, 750
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path, radius=15)
        
        glass.add_text(panel_w//2, 40, "📊 SQLite3 Database Saves",  
                      ('Arial', 24, 'bold'), color='white')
        
        stats_frame = tk.Frame(glass, bg='#34495e', relief='raised', bd=2)
        stats_frame.place(relx=0.5, y=100, anchor='center', width=panel_w-100, height=80)
        
        total_saves = self.data.get_admin_saves_count_sqlite()
        today_saves = self.data.get_today_admin_saves_sqlite()
        
        stats_text = f"📈 TOTAL SQLite3 SAVES: {total_saves} | 📅 TODAY: {today_saves} | 📧 EMAIL SYSTEM: ACTIVE | 🔄 REAL-TIME SYNC: ACTIVE | 📍 LAST UPDATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ⏳ Loading Spinner: READY | ⚡ Performance: OPTIMIZED"
        stats_label = tk.Label(stats_frame, text=stats_text,  
                              font=('Arial', 14, 'bold'), bg='#34495e', fg='white')
        stats_label.pack(expand=True, fill='both')
        
        table_frame = tk.Frame(glass, bg='white')
        table_frame.place(relx=0.5, y=220, anchor='center', width=panel_w-100, height=400)
        
        tree_container = tk.Frame(table_frame, bg='white')
        tree_container.pack(fill='both', expand=True)
        
        h_scrollbar = ttk.Scrollbar(tree_container, orient='horizontal')
        h_scrollbar.pack(side='bottom', fill='x')
        
        v_scrollbar = ttk.Scrollbar(tree_container, orient='vertical')
        v_scrollbar.pack(side='right', fill='y')
        
        # Updated columns to include email data - REMOVED
        columns = ("Save ID", "Student Name", "Phone", "Book Title", "Author", "Issue Date", "Due Date", "Status")
        
        self.reports_tree = ttk.Treeview(tree_container, columns=columns, show='headings', 
                                        height=15, xscrollcommand=h_scrollbar.set,
                                        yscrollcommand=v_scrollbar.set)
        
        col_widths = [80, 150, 100, 200, 150, 100, 100, 80]
        for col, width in zip(columns, col_widths):
            self.reports_tree.heading(col, text=col)
            self.reports_tree.column(col, width=width, minwidth=50, stretch=False)
        
        h_scrollbar.config(command=self.reports_tree.xview)
        v_scrollbar.config(command=self.reports_tree.yview)
        
        self.reports_tree.pack(side='left', fill='both', expand=True)
        
        self.load_reports_data()
        
        action_frame = tk.Frame(glass, bg='gray20')
        action_frame.place(relx=0.5, y=660, anchor='center', width=panel_w-100, height=50)
        
        def view_save_details():
            selection = self.reports_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a save record to view details")
                return
            
            item = self.reports_tree.item(selection[0])
            save_id = item['values'][0]
            
            save_record = None
            for save in self.data.admin_saves:
                if save["save_id"] == save_id:
                    save_record = save
                    break
            
            if save_record:
                # Format email status
                email_sent = save_record.get('email_sent', 0)
                email_status = "✅ Sent" if email_sent > 0 else "❌ Not sent"
                
                details = f"""
                📋 SQLite3 SAVE RECORD DETAILS
                ──────────────────────────────
                🔢 Save ID: {save_record['save_id']}
                🔢 Transaction ID: {save_record['transaction_id']}
                📅 Save Time: {save_record['save_timestamp']}
                
                👤 STUDENT INFORMATION:
                • Student Name: {save_record['student_name']}
                • Phone No.: {save_record['student_phone']}
                • Member ID: {save_record.get('member_id', 'N/A')}
                • Member Type: {save_record.get('member_type', 'N/A')}
                
                📚 BOOK INFORMATION:
                • Book Title: {save_record['book_title']}
                • Author: {save_record['book_author']}
                • ISBN: {save_record['book_isbn']}
                • Book ID: {save_record.get('book_id', 'N/A')}
                • Category: {save_record.get('book_category', 'General')}
                
                📅 TRANSACTION DETAILS:
                • Issue Date: {save_record['issue_date']}
                • Due Date: {save_record['due_date']}
                • Status: {save_record['status']}
                • Fine Amount: ₹{save_record['fine_amount']}
                • Fine Paid: {'Yes' if save_record['fine_paid'] else 'No'}
                • Renewals: {save_record.get('renewals', 0)}
                
                💾 SAVED TO: SQLite3 Database (Auto-saved)
                🔄 REAL-TIME SYNC: ACTIVE
                ⚡ PERFORMANCE: OPTIMIZED WITH CACHING
                """
                
                messagebox.showinfo("SQLite3 Save Record Details", details)
        
        def export_reports_csv():
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile="sqlite3_transaction_saves_report.csv"
            )
            if filename:
                # Show loading spinner
                self.loading_spinner.show("Exporting to CSV...")
                self.root.update()
                
                success = self.admin_saver.export_to_csv(filename)
                
                # Hide spinner
                self.loading_spinner.hide()
                
                if success:
                    messagebox.showinfo("Success", f"SQLite3 reports exported successfully to:\n{filename}")
                else:
                    messagebox.showerror("Error", "Failed to export SQLite3 reports")
        
        def clear_all_saves():
            if messagebox.askyesno("Confirm Clear", 
                                  "Are you sure you want to clear ALL saved transaction data from SQLite3 database?\n\nThis action cannot be undone!"):
                # Show loading spinner
                self.loading_spinner.show("Clearing all saves...")
                self.root.update()
                
                try:
                    self.admin_saver.clear_all_saves()
                    
                    # Hide spinner
                    self.loading_spinner.hide()
                    
                    messagebox.showinfo("Success", "All saved transaction data has been cleared from SQLite3 database")
                    self.load_reports_data()
                except Exception as e:
                    self.loading_spinner.hide()
                    messagebox.showerror("Error", f"Failed to clear saves:\n\n{str(e)}")
        
        def refresh_reports():
            # Show loading spinner
            self.loading_spinner.show("Refreshing database...")
            self.root.update()
            
            try:
                self.data.load_data()
                self.load_reports_data()
                
                # Hide spinner
                self.loading_spinner.hide()
                
                messagebox.showinfo("Refreshed", "SQLite3 database data refreshed successfully")
            except Exception as e:
                self.loading_spinner.hide()
                messagebox.showerror("Error", f"Failed to refresh:\n\n{str(e)}")
        
        details_btn = tk.Button(action_frame, text="👁 View Details", font=('Arial', 11),
                               bg='#3498db', fg='white', command=view_save_details)
        details_btn.pack(side='left', padx=5)
        
        export_btn = tk.Button(action_frame, text="📥 Export CSV", font=('Arial', 11),
                              bg='#27ae60', fg='white', command=export_reports_csv)
        export_btn.pack(side='left', padx=5)
        
        clear_btn = tk.Button(action_frame, text="🗑️ Clear All", font=('Arial', 11),
                             bg='#e74c3c', fg='white', command=clear_all_saves)
        clear_btn.pack(side='left', padx=5)
        
        refresh_btn = tk.Button(action_frame, text="🔄 Refresh SQLite3", font=('Arial', 11),
                               bg='#9b59b6', fg='white', command=refresh_reports)
        refresh_btn.pack(side='right', padx=5)
        
        back_btn = tk.Button(glass, text="← Back to Admin Panel", font=('Arial', 12),  
                            bg='#6c757d', fg='white', command=self.create_admin_screen)
        glass.create_window(panel_w//2, panel_h-50, window=back_btn, anchor='center')
    
    def load_reports_data(self):
        """Load saved transaction data from SQLite3 database into reports table"""
        if hasattr(self, 'reports_tree'):
            for item in self.reports_tree.get_children():
                self.reports_tree.delete(item)
        
        admin_saves = self.data.admin_saves
        
        if not admin_saves:
            self.reports_tree.insert('', 'end', values=(
                "No Data", "", "", "", "", "No saved transactions", "", "", "", ""
            ))
            return
        
        print(f"✅ Loading {len(admin_saves)} save records from SQLite3 database...")
        
        saves = list(reversed(admin_saves))
        
        for save in saves:
            try:
                # Format email status
                email_sent = save.get('email_sent', 0)
                email_status = "✅" if email_sent > 0 else "❌"
                
                self.reports_tree.insert('', 'end', values=(
                    save.get("save_id", ""),
                    save.get("student_name", ""),
                    #save.get("student_email", ""), - REMOVED
                    #email_status, - REMOVED
                    save.get("student_phone", ""),
                    save.get("book_title", ""),
                    save.get("book_author", ""),
                    save.get("issue_date", ""),
                    save.get("due_date", ""),
                    save.get("status", "")
                ))
            except Exception as e:
                print(f"❌ Error inserting SQLite3 save record: {e}")
                continue
    
    # ==================== ADMIN: ACTIVE BORROWERS ====================
    def admin_active_borrowers(self):
        """Admin view of active borrowers with email data"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        bg_path = "voting_bg.jpg"
        self.set_background(bg_path)
        
        panel_w, panel_h = 1150, 700
        
        glass = GlassPanel(self.root, panel_w, panel_h, bg_image_path=bg_path, radius=15)
        
        glass.add_text(panel_w//2, 40, "👥 Active Borrowers (SQLite3 Real-time Data)",  
                      ('Arial', 24, 'bold'), color='white')
        
        stats_frame = tk.Frame(glass, bg='#34495e', relief='raised', bd=2)
        stats_frame.place(relx=0.5, y=100, anchor='center', width=panel_w-100, height=60)
        
        try:
            active_borrowers = self.data.get_active_borrowers_sqlite()
            active_count = len(active_borrowers)
        except Exception as e:
            print(f"❌ Error getting SQLite3 stats: {e}")
            active_count = 0
        
        stats_text = f"📊 ACTIVE BORROWERS: {active_count} | 💾 DATA SOURCE: SQLite3 Database (Real-time) | 📧 EMAIL REMINDERS: ACTIVE | 🔄 Real-time Sync: ACTIVE | ⚡ Performance: OPTIMIZED"
        stats_label = tk.Label(stats_frame, text=stats_text,  
                              font=('Arial', 12, 'bold'), bg='#34495e', fg='white')
        stats_label.pack(expand=True, fill='both', padx=20, pady=10)
        
        table_frame = tk.Frame(glass, bg='white')
        table_frame.place(relx=0.5, y=200, anchor='center', width=panel_w-100, height=380)
        
        tree_container = tk.Frame(table_frame, bg='white')
        tree_container.pack(fill='both', expand=True)
        
        h_scrollbar = ttk.Scrollbar(tree_container, orient='horizontal')
        h_scrollbar.pack(side='bottom', fill='x')
        
        v_scrollbar = ttk.Scrollbar(tree_container, orient='vertical')
        v_scrollbar.pack(side='right', fill='y')
        
        # Updated columns to include email - REMOVED
        columns = ("Student Name", "Phone", "Book Title", "Author", "Issue Date", "Due Date", "Days Left", "Status")
        self.admin_borrowers_tree = ttk.Treeview(tree_container, columns=columns, show='headings', 
                                                height=15, xscrollcommand=h_scrollbar.set,
                                                yscrollcommand=v_scrollbar.set)
        
        col_widths = [150, 120, 200, 150, 100, 100, 80, 80]
        for col, width in zip(columns, col_widths):
            self.admin_borrowers_tree.heading(col, text=col)
            self.admin_borrowers_tree.column(col, width=width, minwidth=50, stretch=False)
        
        h_scrollbar.config(command=self.admin_borrowers_tree.xview)
        v_scrollbar.config(command=self.admin_borrowers_tree.yview)
        
        self.admin_borrowers_tree.pack(side='left', fill='both', expand=True)
        
        def refresh_admin_borrowers():
            for item in self.admin_borrowers_tree.get_children():
                self.admin_borrowers_tree.delete(item)
            
            try:
                active_borrowers = self.data.get_active_borrowers_sqlite()
                today = datetime.now()
                
                for row in active_borrowers:
                    try:
                        due_date = datetime.strptime(row['due_date'], '%Y-%m-%d')
                        days_left = (due_date - today).days
                        
                        if days_left < 0:
                            days_text = f"{-days_left} days overdue"
                            status_color = "Overdue"
                        elif days_left == 0:
                            days_text = "Today"
                            status_color = "Due Today"
                        else:
                            days_text = f"{days_left} days"
                            status_color = "Active"
                    except:
                        days_text = "N/A"
                        status_color = row['status']
                    
                    # Format email status
                    email_sent = row.get('email_sent', 0)
                    email_status = "✅ Sent" if email_sent > 0 else "🔄 Pending"
                    
                    self.admin_borrowers_tree.insert('', 'end', values=(
                        row['student_name'],
                        #row.get('student_email', ''), - REMOVED
                        #email_status, - REMOVED
                        row['student_phone'] or "N/A",
                        row['book_title'],
                        row['book_author'],
                        row['issue_date'],
                        row['due_date'],
                        days_text,
                        status_color
                    ))
                
                total_items = len(self.admin_borrowers_tree.get_children())
                stats_text = f"📊 ACTIVE BORROWERS: {total_items} | 📚 BOOKS CURRENTLY ISSUED: {total_items} | 💾 DATA SOURCE: SQLite3 Database (Updated: {datetime.now().strftime('%H:%M:%S')}) | ⚡ Performance: OPTIMIZED"
                stats_label.config(text=stats_text)
                
            except Exception as e:
                print(f"❌ Error loading from SQLite3: {e}")
                messagebox.showwarning("Database Error", 
                                     f"Could not load from SQLite3 database.\nError: {str(e)}")
                
                for transaction in self.data.transactions:
                    if transaction.get('status') == 'issued':
                        book = self.book_manager.get_book_by_id(transaction['book_id'])
                        book_title = book['title'] if book else "Unknown"
                        book_author = book['author'] if book else "Unknown"
                        book_isbn = book['isbn'] if book else "Unknown"
                        
                        member = self.member_manager.get_member_by_id(transaction['member_id'])
                        member_name = member['name'] if member else "Unknown"
                        member_phone = member['phone'] if member else "N/A"
                        member_email = member.get('email', '') if member else ""
                        
                        try:
                            due_date = datetime.strptime(transaction['due_date'], '%Y-%m-%d')
                            days_left = (due_date - datetime.now()).days
                            
                            if days_left < 0:
                                days_text = f"{-days_left} days overdue"
                                status_color = "Overdue"
                            else:
                                days_text = f"{days_left} days"
                                status_color = "Active"
                        except:
                            days_text = "N/A"
                            status_color = transaction['status']
                        
                        self.admin_borrowers_tree.insert('', 'end', values=(
                            member_name,
                            #member_email, - REMOVED
                            #"N/A", - REMOVED
                            member_phone,
                            book_title,
                            book_author,
                            transaction['issue_date'],
                            transaction['due_date'],
                            days_text,
                            status_color
                        ))
        
        refresh_admin_borrowers()
        
        action_frame = tk.Frame(glass, bg='gray20')
        action_frame.place(relx=0.5, y=620, anchor='center', width=panel_w-100, height=50)
        
        def view_borrower_details():
            selection = self.admin_borrowers_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a borrower to view details")
                return
            
            item = self.admin_borrowers_tree.item(selection[0])
            student_name = item['values'][0]
            book_title = item['values'][4]
            
            try:
                conn = sqlite3.connect(self.data.db_file)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM admin_saves 
                    WHERE student_name = ? AND book_title = ? AND status = 'issued'
                    LIMIT 1
                """, (student_name, book_title))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    row_dict = dict(row)
                    
                    # Calculate days left
                    try:
                        due_date = datetime.strptime(row_dict['due_date'], '%Y-%m-%d')
                        days_left = (due_date - datetime.now()).days
                        if days_left < 0:
                            days_text = f"{-days_left} days overdue"
                        else:
                            days_text = f"{days_left} days left"
                    except:
                        days_text = "N/A"
                    
                    # Email status
                    email_sent = row_dict.get('email_sent', 0)
                    email_status = "✅ Sent" if email_sent > 0 else "❌ Not sent"
                    
                    details = f"""
                    📋 BORROWER DETAILS (From SQLite3)
                    ──────────────────────────────
                    👤 Student Name: {row_dict['student_name']}
                     Phone No.: {row_dict['student_phone'] or 'N/A'}
                    🏷️ Member ID: {row_dict['member_id'] or 'N/A'}
                    📋 Member Type: {row_dict['member_type'] or 'N/A'}
                    
                    📚 BOOK DETAILS:
                    • Book Title: {row_dict['book_title']}
                    • Author: {row_dict['book_author']}
                    • ISBN: {row_dict['book_isbn']}
                    • Category: {row_dict['book_category'] or 'General'}
                    
                    📅 TRANSACTION DETAILS:
                    • Issue Date: {row_dict['issue_date']}
                    • Due Date: {row_dict['due_date']}
                    • Days Status: {days_text}
                    • Status: {row_dict['status']}
                    • Fine Amount: ₹{row_dict['fine_amount']}
                    • Fine Paid: {'Yes' if row_dict['fine_paid'] else 'No'}
                    
                    📧 EMAIL REMINDERS:
                    • Next reminder: Day {min(15 - (datetime.now().date() - datetime.strptime(row_dict['issue_date'], '%Y-%m-%d').date()).days, 15)}
                    • Schedule: Day 5, 10, 15 at 9 AM
                    
                    💾 SAVED TO: SQLite3 Database
                    📅 Saved Time: {row_dict['save_timestamp']}
                    ⚡ PERFORMANCE: OPTIMIZED WITH CACHING
                    """
                    
                    messagebox.showinfo("Borrower Details", details)
                else:
                    messagebox.showinfo("Borrower Details", 
                                       f"Student: {student_name}\nBook: {book_title}\n\nDetails not found in SQLite3 database.")
            
            except Exception as e:
                messagebox.showerror("Error", f"Could not fetch details from SQLite3:\n{str(e)}")
        
        def mark_as_returned():
            selection = self.admin_borrowers_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a book to mark as returned")
                return
            
            item = self.admin_borrowers_tree.item(selection[0])
            student_name = item['values'][0]
            book_title = item['values'][4]
            
            if messagebox.askyesno("Confirm Return", 
                                 f"Mark '{book_title}' as returned for '{student_name}'?\n\nThis will update SQLite3 database and refresh UI automatically."):
                # Show loading spinner
                self.loading_spinner.show(f"Marking '{book_title}' as returned...")
                self.root.update()
                
                try:
                    conn = sqlite3.connect(self.data.db_file)
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        UPDATE admin_saves 
                        SET status = 'returned',
                            return_date = ?
                        WHERE student_name = ? 
                        AND book_title = ? 
                        AND status = 'issued'
                    """, (datetime.now().strftime('%Y-%m-%d'), student_name, book_title))
                    
                    conn.commit()
                    conn.close()
                    
                    # Find the book and update its stock
                    for book in self.data.books:
                        if book['title'] == book_title:
                            book['available_copies'] += 1
                            # Clear cache
                            self.data.book_cache.clear()
                            # Notify observers of stock change
                            self.book_observable.notify_data_change('BOOK_STOCK_UPDATED', book['id'], {
                                'old_stock': book['available_copies'] - 1,
                                'new_stock': book['available_copies'],
                                'book_title': book['title'],
                                'book_author': book['author']
                            })
                            break
                    
                    self.data.save_data()
                    
                    # Hide spinner
                    self.loading_spinner.hide()
                    
                    messagebox.showinfo("Success", "Book marked as returned in SQLite3 database! Stock updated and UI will refresh automatically.")
                    refresh_admin_borrowers()
                    
                except Exception as e:
                    self.loading_spinner.hide()
                    messagebox.showerror("Error", f"Failed to update SQLite3 database:\n{str(e)}")
        
        def export_active_borrowers():
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile="active_borrowers_report.csv"
            )
            if filename:
                # Show loading spinner
                self.loading_spinner.show("Exporting to CSV...")
                self.root.update()
                
                try:
                    data = []
                    for item in self.admin_borrowers_tree.get_children():
                        values = self.admin_borrowers_tree.item(item)['values']
                        data.append(values)
                    
                    with open(filename, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(["Student Name", "Email", "Email Status", "Phone No.", "Book Title", "Author", 
                                        "Issue Date", "Due Date", "Days Left", "Status"])
                        writer.writerows(data)
                    
                    # Hide spinner
                    self.loading_spinner.hide()
                    
                    messagebox.showinfo("Success", f"Active borrowers exported to:\n{filename}")
                except Exception as e:
                    self.loading_spinner.hide()
                    messagebox.showerror("Error", f"Export failed:\n{str(e)}")
        
        details_btn = tk.Button(action_frame, text="👁 View Details", font=('Arial', 11),
                               bg='#3498db', fg='white',
                               command=view_borrower_details)
        details_btn.pack(side='left', padx=5)
        
        return_btn = tk.Button(action_frame, text="📚 Mark Returned", font=('Arial', 11),
                              bg='#27ae60', fg='white',
                              command=mark_as_returned)
        return_btn.pack(side='left', padx=5)
        
        export_btn = tk.Button(action_frame, text="📥 Export CSV", font=('Arial', 11),
                              bg='#f39c12', fg='white',
                              command=export_active_borrowers)
        export_btn.pack(side='left', padx=5)
        
        refresh_btn = tk.Button(action_frame, text="🔄 Refresh SQLite3", font=('Arial', 11),
                               bg='#e74c3c', fg='white',
                               command=refresh_admin_borrowers)
        refresh_btn.pack(side='right', padx=5)
        
        back_btn = tk.Button(glass, text="← Back to Admin Panel", font=('Arial', 12),  
                            bg='#6c757d', fg='white', command=self.create_admin_screen)
        glass.create_window(panel_w//2, panel_h-50, window=back_btn, anchor='center')
    
    def change_admin_password(self):
        """Change admin password"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Change Admin Password")
        dialog.geometry("400x300")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="🔑 Change Admin Password",  
                 font=('Arial', 16, 'bold'), bg='white', fg='#2c3e50').pack(pady=20)
        
        tk.Label(dialog, text="Current Password:",  
                 font=('Arial', 11), bg='white').pack(anchor='w', padx=30)
        current_entry = tk.Entry(dialog, font=('Arial', 12), show="*", width=25)
        current_entry.pack(pady=5, padx=30)
        
        tk.Label(dialog, text="New Password:",  
                 font=('Arial', 11), bg='white').pack(anchor='w', padx=30, pady=(10,0))
        new_entry = tk.Entry(dialog, font=('Arial', 12), show="*", width=25)
        new_entry.pack(pady=5, padx=30)
        
        tk.Label(dialog, text="Confirm New Password:",  
                 font=('Arial', 11), bg='white').pack(anchor='w', padx=30, pady=(10,0))
        confirm_entry = tk.Entry(dialog, font=('Arial', 12), show="*", width=25)
        confirm_entry.pack(pady=5, padx=30)
        
        def update_password():
            current = current_entry.get().strip()
            new = new_entry.get().strip()
            confirm = confirm_entry.get().strip()
            
            if not all([current, new, confirm]):
                messagebox.showerror("Error", "Please fill in all fields")
                return
                
            if current != self.admin_password:
                messagebox.showerror("Error", "Current password is incorrect")
                return
                
            if new != confirm:
                messagebox.showerror("Error", "New passwords do not match")
                return
                
            if len(new) < 4:
                messagebox.showerror("Error", "New password must be at least 4 characters")
                return
                
            self.admin_password = new
            self.data.save_data()
            
            messagebox.showinfo("Success", "Admin password updated successfully!")
            dialog.destroy()
        
        button_frame = tk.Frame(dialog, bg='white')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Update Password", font=('Arial', 12),  
                  bg='#27ae60', fg='white', command=update_password).pack(side='left', padx=5)
        tk.Button(button_frame, text="Cancel", font=('Arial', 12),  
                  bg='#95a5a6', fg='white', command=dialog.destroy).pack(side='left', padx=5)

# ==================== MAIN APPLICATION ====================
if __name__ == "__main__":
    root = tk.Tk()
    
    root.withdraw()
    
    app = LibraryManagementSystem(root)
    
    root.deiconify()
    
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    # Set up window close handler to stop email scheduler
    def on_closing():
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    root.mainloop()
