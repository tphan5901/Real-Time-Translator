import soundcard as sc
import soundfile as sf

output_filename = "temp_audio.wav"
samplerate = 48000
record_sec = 200

#60 sec = 1min. 60 * 5 = 300 = 5minutes
with sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True).recorder(samplerate=samplerate) as mic:
   #record audio w/ loopback from default speaker
    data = mic.record(numframes=samplerate*record_sec)
    #change "data = data[:0,0] to "data= data" if you would like to write audio to multiple channels"
    sf.write(file=output_filename, data=data[: ,0], samplerate=samplerate)

    # "ctrl + c " to exit the program recording in terminal