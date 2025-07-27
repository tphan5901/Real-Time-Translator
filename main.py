import os
import tkinter as tk
import sounddevice as sd
import numpy as np
import threading
import wave
import speech_recognition as sr
import pykakasi
import whisper #\base whisper model: time(3.5 - 4secs)
#from faster_whisper import WhisperModel
import soundcard as sc
from tkinter import filedialog
from PIL import Image, ImageTk
import concurrent.futures
from queue import Queue
import concurrent.futures
from deepseek import *

AUDIO_FILENAME = "temp_audio.wav"
SAMPLERATE = 44100
CHANNELS = 2
MAX_WORKERS = 8

# List all input devices
#print(sd.query_devices())

# Select the VB-Cable Input
vb_device_index = None
for i, dev in enumerate(sd.query_devices()):
    if "CABLE Output" in dev['name'] and dev['max_input_channels'] > 0:
        vb_device_index = i
        print(f"Found VB Cable Input at index {vb_device_index}")
        break

class TranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Two Way Translator")
        self.recording = False
        self.audio_queue = Queue(maxsize = 20)

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

        # Start workers
        for _ in range(MAX_WORKERS):
            self.executor.submit(self.audio_worker)

        # Create main frame that will contain canvas and widgets
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)
        
        # Create canvas for background - with highlightthickness=0 to remove border
        self.canvas = tk.Canvas(self.main_frame, highlightthickness=0, bd = 0)
        self.canvas.pack(fill="both", expand=True)
        
        # Initialize background image
        self.bg_image = None
        self.bg_photo = None
        
        # Create a truly transparent frame for widgets
        self.widget_frame = tk.Frame(self.canvas, bg='', highlightthickness=0, bd = 0)
        # Place the widget frame using create_window (not pack/grid)
        self.widget_window = self.canvas.create_window(
            0, 0, 
            window=self.widget_frame, 
            anchor="nw", 
            tags="widget_frame"
        )

        # Initialize output devices first
        self.output_devices = [d['name'] for d in sd.query_devices() if d['max_output_channels'] > 0]
        self.selected_output_device = tk.StringVar()
        
        # Initialize mic input devices
        self.device_name_to_index = {
            dev['name']: idx
            for idx, dev in enumerate(sd.query_devices())
            if dev['max_input_channels'] > 0
        }

        # Set default output device
        if self.output_devices:
            self.selected_output_device.set(self.output_devices[0])  
        else:
            self.output_devices = ["No Output Devices Found"]
            self.selected_output_device.set(self.output_devices[0])

        # Now create all widgets as children of widget_frame
        tk.Button(self.widget_frame, text="Choose Background", command=self.choose_background).pack(pady=10, anchor='w', padx=10)

        #dropdown menu for playback device selection
        tk.Label(self.widget_frame, text="Select Playback Device:", font=("Arial", 12)).pack(pady=(10, 0), anchor='w', padx=5)
        self.output_dropdown = tk.OptionMenu(
            self.widget_frame,
            self.selected_output_device,
            *self.output_devices,
            command=self.on_output_device_change
        )
        self.output_dropdown.config(
            width=50,
            bg="#FF9500",
            fg="white",
            activebackground="#A66C23",  # optional: color when clicked
            activeforeground="white"     # optional: text color when clicked
        )
        self.output_dropdown.pack(pady=(0, 10), anchor='w', padx=10)

        self.active_system_device_index = None 

        # Toggle System Audio Recording Button
        self.system_audio_enabled = False
        self.system_audio_btn = tk.Button(
            self.widget_frame, 
            text="Enable System Audio Recording", 
            bg = "#0D82EF",
            fg = "white",
            activebackground="#244EA2",  # optional: color when clicked
            activeforeground="white",     # optional: text color when clicked
            width=30, 
            height=2, 
            command=self.toggle_system_audio
        )
        self.system_audio_btn.pack(pady=(10, 0), anchor='w', padx=10)

        # Mic input Button
        self.label = tk.Label(
            self.widget_frame, 
            text="Hold the Button to speak", 
            font=("Arial", 12)
        )
        self.label.pack(pady=(10, 0), anchor='w', padx=10)  
        self.record_btn = tk.Button(
            self.widget_frame, 
            text=" Hold to Record", 
            bg = "#3ED943",
            fg = "white",
            activebackground="#1E894E",  # optional: color when clicked
            activeforeground="white",     # optional: text color when clicked
            width=20, 
            height=2
        )
        self.record_btn.pack(pady=(10,0), padx=10, anchor='w')


        self.record_btn.bind('<ButtonPress>', self.start_recording)
        self.record_btn.bind('<ButtonRelease>', self.stop_recording)

      # Window size
        root.geometry("800x1045")
      #  root.resizable(False, False)
      #  root.attributes("-toolwindow", True)  
        self.root.bind('<Configure>', self.on_resize)

      #captures system audio using vb audio cable
        self.stream = sd.InputStream(
            device=vb_device_index,
            samplerate=SAMPLERATE,
            channels=CHANNELS,
            dtype='int16',
            callback=self.callback)
    
        #textbox
        self.output_textbox = tk.Text(
            self.widget_frame, 
            font=("Arial", 12), 
            width=35, 
            height=2,
            wrap=tk.WORD,
            bg='white',
            padx=10,
            pady=5
        )
        self.output_textbox.pack(pady=15, anchor='w', padx=10) #pad around the component
        self.output_textbox.insert(tk.END, "Translation results will appear here")
        self.output_textbox.config(state='disabled') 

    def audio_worker(self):
        while True:
            try: 
                chunk = self.audio_queue.get()
                if chunk is None:
                    break
                self.process_chunk(chunk)
            except Exception as e:
                print(f"Error: Worker failed: {e}")

    def on_resize(self, event):
        if self.bg_image:
            # Resize the background image
            new_img = self.bg_image.resize((event.width, event.height), Image.Resampling.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(new_img)
            
            # Update canvas background
            self.canvas.delete("bg_image")
            self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="bg_image")
            self.canvas.lower("bg_image") 
            
            # Update widget frame position
            self.canvas.tag_raise("widget_frame")

    def choose_background(self):
        filepath = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")])
        if filepath:
            self.bg_image = Image.open(filepath)
            # Get current window size
            window_width = self.root.winfo_width()
            window_height = self.root.winfo_height()
            
            # Resize image to window dimensions
            self.bg_image = self.bg_image.resize((window_width, window_height), Image.Resampling.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(self.bg_image)
            
            # Clear any existing background
            self.canvas.delete("bg_image")
            
            # Update canvas size and add new background
            self.canvas.config(width=window_width, height=window_height)
            self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="bg_image")
            self.canvas.lower("bg_image")  # Ensure it stays behind everything
            
            # Make sure widgets stay on top
            self.canvas.tag_raise("widget_frame")

    def on_output_device_change(self, selected_device_name):
        print(f"[INFO] Output device selected: {selected_device_name}")

        # Start or restart VB-Cable monitoring
        if hasattr(self, 'vb_recording') and self.vb_recording:
            self.vb_recording = False
            print("[INFO] Stopping previous system audio monitor...")

        self.vb_recording = True
        self.vb_frames = []

        # Start system audio recording in new thread
        threading.Thread(target=self.background_system_audio, daemon=True).start()
        self.system_audio_enabled = True
        self.system_audio_btn.config(text="Disable System Audio Recording")
        self.label.config(text="System Audio Recording Enabled (via dropdown)")

    def background_system_audio(self):
        try:
            with sd.InputStream(device=vb_device_index, samplerate=SAMPLERATE, channels=CHANNELS, dtype='int16') as stream:
                print("[INFO] Monitoring system audio through VB-Cable...")

                while self.vb_recording:
                    audio_chunk = stream.read(int(SAMPLERATE * 5))[0]  # 5 seconds
                    self.vb_frames.append(audio_chunk)

                    if not self.audio_queue.full():
                        self.audio_queue.put(audio_chunk.copy())
                    else:
                        print("Warning: Audio queue is full. Dropping Chunk")
                    # Save WAV
                 #   combined = np.concatenate(self.vb_frames, axis=0)
                 #   wf = wave.open(AUDIO_FILENAME, 'wb')
                 #   wf.setnchannels(CHANNELS)
                 #   wf.setsampwidth(2)
                 #   wf.setframerate(SAMPLERATE)
                 #   wf.writeframes(combined.tobytes())
                 #   wf.close()

                    # Transcribe + Translate
                #    self.process_system_audio()
                #    self.vb_frames = []  # Clear buffer
        except Exception as e:
            print(f"[ERROR] VB-Cable stream failed: {e}")

    def toggle_system_audio(self):
        if not self.system_audio_enabled:
            # Enable system audio recording
            device_index = vb_device_index
            if device_index is None:
                self.label.config(text="[ERROR] VB-Cable input device not found.")
                return

            try:
                self.system_stream = sd.InputStream(
                    device=device_index,
                    samplerate=SAMPLERATE,
                    channels=CHANNELS,
                    dtype='int16',
                    callback=self.callback
                )
                self.frames = []  # Clear buffer
                self.system_stream.start()

                # Start VB-Cable monitoring
                if hasattr(self, 'vb_recording') and self.vb_recording:
                    self.vb_recording = False  # stop old thread if running

                self.vb_recording = True
                self.vb_frames = []
                threading.Thread(target=self.background_system_audio, daemon=True).start()

                self.system_audio_enabled = True
                self.active_system_device_index = device_index
                self.system_audio_btn.config(text="Disable System Audio Recording")
                self.label.config(text="System Audio Recording Enabled")

            except Exception as e:
                self.label.config(text=f"[ERROR] Failed to start system stream: {e}")
        else:
            # Disable system audio recording
            try:
                if self.system_stream:
                    self.system_stream.stop()
                    self.system_stream.close()
            except Exception as e:
                self.label.config(text=f"[WARNING] Failed to stop system stream: {e}")

            #Stop VB-Cable monitoring thread
            self.vb_recording = False

            self.system_audio_enabled = False
            self.active_system_device_index = None
            self.system_audio_btn.config(text="Enable System Audio Recording")
            self.label.config(text="System Audio Recording Disabled")

    def start_recording(self, event):
        self.recording = True
        self.label.config(text="Recording...")
        self.frames = []
        self.stream = sd.InputStream(samplerate=SAMPLERATE, channels=CHANNELS, dtype='int16', callback=self.callback)
        self.stream.start()

    def stop_recording(self, event):                                                                
        self.recording = False
        self.stream.stop()
        self.stream.close()
        self.save_audio()
        self.label.config(text="Transcribing...")
        #when we stop recording audio, start processing audio on seperate thread
        threading.Thread(target=self.process_audio).start()


    def convert_to_romaji(self, japanese_text):
        """Convert Japanese text to spaced Romaji"""
        kakasi = pykakasi.kakasi()
        kakasi.setMode("H", "a")  # Hiragana to ascii
        kakasi.setMode("K", "a")  # Katakana to ascii
        kakasi.setMode("J", "a")  # Kanji to ascii
        kakasi.setMode("r", "Hepburn")  # Use Hepburn Romanization
        converter = kakasi.getConverter()
        
        # Convert to Romaji
        romaji = converter.do(japanese_text)
        
        # Add spaces between words (basic implementation)
        spaced_romaji = ""
        for i, char in enumerate(romaji):
            # Add space before uppercase letters (except first character)
            if i > 0 and char.isupper() and romaji[i-1].islower():
                spaced_romaji += " " + char
            # Add space after particles
            elif char in ('wa', 'ga', 'no', 'ni', 'de', 'wo', 'e', 'to', 'ya', 'ka'):
                spaced_romaji += char + " "
            else:
                spaced_romaji += char
        
        # Clean up any double spaces
        spaced_romaji = " ".join(spaced_romaji.split())
        
        return spaced_romaji

    def callback(self, indata, frames, time, status):
        if self.recording:
            self.frames.append(indata.copy())
           # print("Audio captured (shape:", indata.shape, ") First 5 samples:", indata[:5])

    #saves audio to temp_audio
    def save_audio(self):
        audio = np.concatenate(self.frames, axis=0)
        wf = wave.open(AUDIO_FILENAME, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(SAMPLERATE)
        wf.writeframes(audio.tobytes())
        wf.close()

    #whisper ai to transcribes recorded mic input device to text
    def process_audio(self):
        try:
            model = whisper.load_model("tiny.en")  # or "tiny.en" for speed or base which is slower
            result = model.transcribe(AUDIO_FILENAME, language="en")
            english_text = result["text"]
        except Exception as e:
            english_text = f"[ERROR] Transcription failed: {e}"

        if not english_text.startswith("[ERROR]"):
            japanese_text = self.translate_with_deepseek(english_text)
        else:
            japanese_text = ""

        romaji = self.convert_to_romaji(japanese_text)
        self.root.after(0, self.update_output, english_text, japanese_text, romaji)
        
    #use whisper to transcribe text format from selected playback device on targeted languages 
    def process_system_audio(self):
        try:
            model = whisper.load_model("tiny.en") #tiny.en or base
            result = model.transcribe(AUDIO_FILENAME, language="ja")
            japanese_text = result["text"]
        except Exception as e:
            japanese_text = f"[ERROR] Transcription failed: {e}"

        if not japanese_text.startswith("[ERROR]"):
            english_text = self.translate_japanese_to_english(japanese_text)
        else:
            english_text = ""

        romaji = self.convert_to_romaji(japanese_text) if not japanese_text.startswith("[ERROR]") else ""
        self.root.after(0, self.update_output, english_text, japanese_text, romaji)

    def translate_japanese_to_english(self, text):
        try:
            messages = [ 
                {"role": "system", "content": "You are a translation tool. Translate the following Japanese text to English Romanji reading without conversationally replying back to the text."}, #assistant
                {"role": "user", "content": text}
            ]
            translation = ask_deepseek(messages)
            if "ですか" in text and "?" not in translation:
                translation = translation.replace(".", "?")
            return translation
        except Exception as e:
            return f"[ERROR] Translation failed: {e}"

    def update_output(self, english, japanese, romaji):
        self.output_textbox.config(state='normal')
        self.output_textbox.delete(1.0, tk.END)

        formatted_text = f"English: {english}\n\nJapanese: {japanese}\n\nRomaji: {romaji}"
        self.output_textbox.insert(tk.END, formatted_text)

        # Count number of lines to adjust textbox height
        line_count = int(self.output_textbox.index('end-1c').split('.')[0])
        new_height = min(max(line_count, 2), 30)  # between 2 and 30 lines
        self.output_textbox.config(height=new_height)

        self.output_textbox.config(state='disabled')
        self.output_textbox.see(tk.END)

        self.widget_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))


if __name__ == "__main__":
    start_ollama() 
    root = tk.Tk()
    app = TranslatorApp(root)
 
 
    def on_closing():
        app.vb_recording = False
        stop_ollama()  
        for _ in range(MAX_WORKERS):
            app.audio_queue.put(None)
        app.executor.shutdown(wait=True)
        os._exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()