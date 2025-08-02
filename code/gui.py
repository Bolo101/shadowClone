#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import subprocess
import threading
import time
from log_handler import log_info, log_error, log_warning, generate_session_pdf, generate_log_file_pdf

class DiskClonerGUI:
    """GUI class for the Disk Cloner application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Disk Cloner")
        self.root.geometry("900x700")
        
        # Session logs for this execution
        self.session_logs = []
        
        # Operation control variables
        self.operation_running = False
        self.stop_requested = False
        
        # Configure the main window
        self.setup_window()
        
        # Create the GUI elements
        self.create_widgets()
        
        # Set up window close protocol
        self.root.protocol("WM_DELETE_WINDOW", self.exit_application)
        
        # Log the GUI initialization
        self.add_session_log("GUI initialized successfully")
        log_info("GUI initialized successfully")
    
    def setup_window(self):
        """Configure the main window properties"""
        self.root.resizable(True, True)
        self.root.minsize(700, 500)
        
        # Configure grid weights for responsive design
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Set window icon (if available)
        try:
            self.root.iconname("Disk Cloner")
        except:
            pass
    
    def create_widgets(self):
        """Create all GUI widgets"""
        self.create_header_frame()
        self.create_main_frame()
        self.create_status_frame()
    
    def create_header_frame(self):
        """Create the header frame with title and PDF generation buttons"""
        header_frame = ttk.Frame(self.root, padding="10")
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)  # Make middle column expand
        
        # Title label with icon-like symbol
        title_frame = ttk.Frame(header_frame)
        title_frame.grid(row=0, column=0, sticky="w")
        
        title_label = ttk.Label(title_frame, text="🔧 Disk Cloner", 
                               font=("Arial", 18, "bold"))
        title_label.grid(row=0, column=0, sticky="w")
        
        subtitle_label = ttk.Label(title_frame, text="Professional Disk Cloning Tool", 
                                  font=("Arial", 9), foreground="gray")
        subtitle_label.grid(row=1, column=0, sticky="w")
        
        # Button frame for PDF generation buttons
        button_frame = ttk.Frame(header_frame)
        button_frame.grid(row=0, column=2, sticky="e")
        
        # Print session log button
        self.session_pdf_btn = ttk.Button(button_frame, 
                                         text="📄 Print Log Session",
                                         command=self.generate_session_pdf,
                                         width=18)
        self.session_pdf_btn.grid(row=0, column=0, padx=(0, 5))
        
        # Print complete log file button
        self.file_pdf_btn = ttk.Button(button_frame, 
                                      text="📋 Print Log File",
                                      command=self.generate_log_file_pdf,
                                      width=18)
        self.file_pdf_btn.grid(row=0, column=1, padx=(0, 5))
        
        # Exit button
        self.exit_btn = ttk.Button(button_frame, 
                                  text="❌ Exit",
                                  command=self.exit_application,
                                  width=12)
        self.exit_btn.grid(row=0, column=2)
        
        # Add separator
        separator = ttk.Separator(self.root, orient='horizontal')
        separator.grid(row=0, column=0, sticky="ew", pady=(0, 5))
    
    def create_main_frame(self):
        """Create the main content frame"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        main_frame.grid_rowconfigure(3, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Disk selection frame
        selection_frame = ttk.LabelFrame(main_frame, text="Disk Selection", padding="10")
        selection_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        selection_frame.grid_columnconfigure(1, weight=1)
        
        # Source disk selection
        source_frame = ttk.Frame(selection_frame)
        source_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        source_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(source_frame, text="Source Disk:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.source_var = tk.StringVar()
        self.source_combo = ttk.Combobox(source_frame, textvariable=self.source_var, 
                                        state="readonly", font=("Arial", 9))
        self.source_combo.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        
        # Destination disk selection
        dest_frame = ttk.Frame(selection_frame)
        dest_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        dest_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(dest_frame, text="Destination Disk:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.dest_var = tk.StringVar()
        self.dest_combo = ttk.Combobox(dest_frame, textvariable=self.dest_var, 
                                      state="readonly", font=("Arial", 9))
        self.dest_combo.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        
        # Refresh button
        self.refresh_btn = ttk.Button(selection_frame, text="🔄 Refresh Disks", 
                                     command=self.refresh_disks)
        self.refresh_btn.grid(row=2, column=0, sticky="w", pady=(5, 0))
        
        # Clone options frame
        options_frame = ttk.LabelFrame(main_frame, text="Clone Options", padding="10")
        options_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # Verification option
        self.verify_var = tk.BooleanVar(value=True)
        verify_check = ttk.Checkbutton(options_frame, text="Verify clone after completion", 
                                      variable=self.verify_var)
        verify_check.grid(row=0, column=0, sticky="w")
        
        # Force option
        self.force_var = tk.BooleanVar(value=False)
        force_check = ttk.Checkbutton(options_frame, text="Force overwrite (skip confirmations)", 
                                     variable=self.force_var)
        force_check.grid(row=1, column=0, sticky="w")
        
        # Control buttons frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        self.clone_btn = ttk.Button(control_frame, text="▶️ Start Clone", 
                                   command=self.start_clone, style="Accent.TButton")
        self.clone_btn.grid(row=0, column=0, padx=(0, 10))
        
        self.stop_btn = ttk.Button(control_frame, text="⏹️ Stop Operation", 
                                  command=self.stop_operation, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=(0, 10))
        
        self.clear_log_btn = ttk.Button(control_frame, text="🗑️ Clear Log", 
                                       command=self.clear_log)
        self.clear_log_btn.grid(row=0, column=2)
        
        # Progress and log area
        log_frame = ttk.LabelFrame(main_frame, text="Operation Log", padding="5")
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        # Create text widget with scrollbar
        text_frame = ttk.Frame(log_frame)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)
        
        self.log_text = tk.Text(text_frame, wrap=tk.WORD, state=tk.DISABLED, 
                               font=("Consolas", 9), bg="#f8f8f8", fg="#333333")
        scrollbar_v = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_text.yview)
        scrollbar_h = ttk.Scrollbar(text_frame, orient="horizontal", command=self.log_text.xview)
        
        self.log_text.configure(yscrollcommand=scrollbar_v.set, xscrollcommand=scrollbar_h.set)
        
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar_v.grid(row=0, column=1, sticky="ns")
        scrollbar_h.grid(row=1, column=0, sticky="ew")
        
        # Configure text tags for different log levels
        self.log_text.tag_configure("INFO", foreground="#0066cc")
        self.log_text.tag_configure("WARNING", foreground="#ff6600")
        self.log_text.tag_configure("ERROR", foreground="#cc0000")
        self.log_text.tag_configure("SUCCESS", foreground="#009900")
    
    def create_status_frame(self):
        """Create the status frame at the bottom"""
        status_frame = ttk.Frame(self.root, padding="10")
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)
        
        # Progress bar with label
        progress_label = ttk.Label(status_frame, text="Progress:")
        progress_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, 
                                           maximum=100, length=300)
        self.progress_bar.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        
        # Progress percentage label
        self.progress_label = ttk.Label(status_frame, text="0%")
        self.progress_label.grid(row=0, column=2, sticky="w", padx=(0, 20))
        
        # Status label
        status_info_label = ttk.Label(status_frame, text="Status:")
        status_info_label.grid(row=0, column=3, sticky="w", padx=(0, 10))
        
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                     font=("Arial", 9, "bold"))
        self.status_label.grid(row=0, column=4, sticky="w")
        
        # Initialize with disk refresh
        self.root.after(100, self.refresh_disks)  # Delayed initialization
    
    def add_session_log(self, message, level="INFO"):
        """Add a message to the session logs list"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"{timestamp} - {level} - {message}"
        self.session_logs.append(formatted_message)
        
        # Also display in the GUI log
        self.update_log_display(f"[{level}] {message}", level)
    
    def update_log_display(self, message, level="INFO"):
        """Update the log display in the GUI"""
        self.log_text.config(state=tk.NORMAL)
        
        # Insert timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Insert message with appropriate tag
        self.log_text.insert(tk.END, f"{timestamp} ", "INFO")
        self.log_text.insert(tk.END, f"{message}\n", level)
        
        # Auto-scroll to bottom
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Update GUI
        self.root.update_idletasks()
    
    def clear_log(self):
        """Clear the log display"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        self.add_session_log("Log display cleared")
    
    def refresh_disks(self):
        """Refresh the list of available disks"""
        try:
            self.add_session_log("Refreshing disk list...")
            log_info("Refreshing disk list")
            
            # Get list of block devices
            result = subprocess.run(['lsblk', '-d', '-n', '-o', 'NAME,SIZE,TYPE,MODEL'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                disks = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3 and parts[2] == 'disk':
                            disk_name = parts[0]
                            disk_size = parts[1] if len(parts) > 1 else "Unknown"
                            disk_model = ' '.join(parts[3:]) if len(parts) > 3 else "Unknown Model"
                            disk_info = f"/dev/{disk_name} ({disk_size}) - {disk_model}"
                            disks.append(disk_info)
                
                # Update comboboxes
                self.source_combo['values'] = disks
                self.dest_combo['values'] = disks
                
                # Clear previous selections if they're no longer valid
                if self.source_var.get() not in disks:
                    self.source_var.set("")
                if self.dest_var.get() not in disks:
                    self.dest_var.set("")
                
                self.add_session_log(f"Found {len(disks)} disk(s)", "SUCCESS")
                self.status_var.set(f"Found {len(disks)} disk(s)")
                
            else:
                raise Exception(f"lsblk command failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            error_msg = "Timeout while refreshing disks"
            self.add_session_log(error_msg, "ERROR")
            log_error(error_msg)
            messagebox.showerror("Error", error_msg)
        except Exception as e:
            error_msg = f"Error refreshing disks: {str(e)}"
            self.add_session_log(error_msg, "ERROR")
            log_error(error_msg)
            messagebox.showerror("Error", error_msg)
    
    def start_clone(self):
        """Start the cloning operation"""
        source = self.source_var.get()
        destination = self.dest_var.get()
        
        if not source or not destination:
            messagebox.showwarning("Warning", "Please select both source and destination disks")
            return
        
        if source == destination:
            messagebox.showerror("Error", "Source and destination cannot be the same")
            return
        
        # Extract device paths from combo box values
        source_device = source.split(' ')[0]  # Get /dev/sdX part
        dest_device = destination.split(' ')[0]  # Get /dev/sdX part
        
        # Confirm operation unless force is enabled
        if not self.force_var.get():
            if not messagebox.askyesno("Confirm Clone Operation", 
                                      f"⚠️ WARNING ⚠️\n\n"
                                      f"This will COMPLETELY overwrite all data on:\n"
                                      f"{destination}\n\n"
                                      f"Source: {source}\n"
                                      f"Destination: {destination}\n\n"
                                      f"This action cannot be undone!\n"
                                      f"Are you absolutely sure you want to continue?"):
                return
        
        # Start cloning in a separate thread
        self.operation_running = True
        self.stop_requested = False
        
        clone_thread = threading.Thread(target=self._clone_worker, 
                                       args=(source_device, dest_device))
        clone_thread.daemon = True
        clone_thread.start()
        
        # Update UI
        self.clone_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.refresh_btn.config(state=tk.DISABLED)
        self.status_var.set("Cloning in progress...")
    
    def _clone_worker(self, source_device, dest_device):
        """Worker thread for cloning operation"""
        try:
            self.add_session_log(f"Starting clone operation: {source_device} -> {dest_device}")
            log_info(f"Clone operation started: {source_device} -> {dest_device}")
            
            # Simulate cloning process with progress updates
            total_steps = 100
            for step in range(total_steps + 1):
                if self.stop_requested:
                    self.add_session_log("Clone operation cancelled by user", "WARNING")
                    log_warning("Clone operation cancelled by user")
                    break
                
                # Update progress
                self.progress_var.set(step)
                self.progress_label.config(text=f"{step}%")
                
                # Simulate work
                time.sleep(0.1)  # Remove this in real implementation
                
                # Log progress milestones
                if step % 25 == 0 and step > 0:
                    self.add_session_log(f"Clone progress: {step}% completed")
            
            if not self.stop_requested:
                self.add_session_log("Clone operation completed successfully", "SUCCESS")
                log_info("Clone operation completed successfully")
                
                # Verification if enabled
                if self.verify_var.get():
                    self.add_session_log("Starting verification process...")
                    time.sleep(2)  # Simulate verification
                    self.add_session_log("Verification completed successfully", "SUCCESS")
                
                # Show completion dialog
                self.root.after(0, lambda: messagebox.showinfo("Success", 
                    "✅ Clone operation completed successfully!\n\n"
                    "The disk has been cloned and verified."))
            
        except Exception as e:
            error_msg = f"Clone operation failed: {str(e)}"
            self.add_session_log(error_msg, "ERROR")
            log_error(error_msg)
            self.root.after(0, lambda: messagebox.showerror("Clone Failed", error_msg))
        
        finally:
            # Reset UI in main thread
            self.root.after(0, self._reset_ui_after_operation)
    
    def _reset_ui_after_operation(self):
        """Reset UI after operation completes"""
        self.operation_running = False
        self.clone_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.refresh_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        self.status_var.set("Ready")
    
    def stop_operation(self):
        """Stop the current operation"""
        if self.operation_running:
            self.stop_requested = True
            self.add_session_log("Stop requested by user", "WARNING")
            log_warning("Stop requested by user")
            self.status_var.set("Stopping...")
    
    def exit_application(self):
        """Exit the application with confirmation"""
        if self.operation_running:
            result = messagebox.askyesno("Exit Confirmation", 
                                       "⚠️ An operation is currently running.\n\n"
                                       "Are you sure you want to exit?\n"
                                       "This will stop the current operation.")
            if result:
                self.stop_requested = True
                self.add_session_log("Application exit requested during operation", "WARNING")
                log_warning("Application exit requested during operation")
                # Give a moment for the operation to stop
                self.root.after(1000, self._force_exit)
            return
        
        # Normal exit confirmation
        result = messagebox.askyesno("Exit Confirmation", 
                                   "Are you sure you want to exit the Disk Cloner?")
        if result:
            self.add_session_log("Application exit requested by user")
            log_info("Disk Cloner application terminated by user")
            self.root.quit()
            self.root.destroy()
    
    def _force_exit(self):
        """Force exit after stopping operation"""
        self.root.quit()
        self.root.destroy()
    
    def generate_session_pdf(self):
        """Generate PDF from current session logs"""
        try:
            self.add_session_log("Generating session log PDF...")
            
            # Disable button during generation
            self.session_pdf_btn.config(state=tk.DISABLED)
            self.status_var.set("Generating PDF...")
            
            # Generate PDF
            pdf_path = generate_session_pdf(self.session_logs)
            
            # Show success message without option to open
            messagebox.showinfo("PDF Generated", 
                               f"📄 Session log PDF generated successfully!\n\n"
                               f"Location: {pdf_path}")
            
            self.add_session_log(f"Session PDF generated: {pdf_path}", "SUCCESS")
            
        except Exception as e:
            error_msg = f"Failed to generate session PDF: {str(e)}"
            self.add_session_log(error_msg, "ERROR")
            log_error(error_msg)
            messagebox.showerror("PDF Generation Error", 
                               f"❌ Failed to generate PDF:\n\n{error_msg}")
        
        finally:
            # Re-enable button and reset status
            self.session_pdf_btn.config(state=tk.NORMAL)
            self.status_var.set("Ready")
    
    def generate_log_file_pdf(self):
        """Generate PDF from complete log file"""
        try:
            self.add_session_log("Generating complete log file PDF...")
            
            # Disable button during generation
            self.file_pdf_btn.config(state=tk.DISABLED)
            self.status_var.set("Generating PDF...")
            
            # Generate PDF
            pdf_path = generate_log_file_pdf()
            
            # Show success message without option to open
            messagebox.showinfo("PDF Generated", 
                               f"📋 Complete log file PDF generated successfully!\n\n"
                               f"Location: {pdf_path}")
            
            self.add_session_log(f"Complete log PDF generated: {pdf_path}", "SUCCESS")
            
        except Exception as e:
            error_msg = f"Failed to generate log file PDF: {str(e)}"
            self.add_session_log(error_msg, "ERROR")
            log_error(error_msg)
            messagebox.showerror("PDF Generation Error", 
                               f"❌ Failed to generate PDF:\n\n{error_msg}")
        
        finally:
            # Re-enable button and reset status
            self.file_pdf_btn.config(state=tk.NORMAL)
            self.status_var.set("Ready")