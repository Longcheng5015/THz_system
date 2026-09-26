# THz FFT function test script
import numpy as np


def thz_fft(position_mm, TDS_amplitude):
    """Here, multi-steps scan is taken into considuration for FFT processing.
       The resolution is find the smallest step size in position_mm and use it as new_time_step.
       Use the new_time_step to interpolate TDS_amplitude and then perform FFT processing."""
    
    c = 3e8  # speed of light in m/s
    time_ps = 2 * position_mm * 1e-3 / c * 1e12  # convert position in mm to time in ps (round-trip)
    time_step_min = np.min(np.diff(time_ps))  # find the minimum time step in ps
    time_step_uniform = np.arange(time_ps.min(), time_ps.max(), time_step_min)  # uniform time steps
    TDS_amplitude_interp = np.interp(time_step_uniform, time_ps, TDS_amplitude)  # interpolate amplitude

    # Perform FFT
    Num_amp = len(TDS_amplitude_interp) # Number of sample points
    amp_FDS = np.fft.fft(TDS_amplitude_interp)
    freq = np.fft.fftfreq(Num_amp, time_step_uniform[1] - time_step_uniform[0])  # frequency bins in THz

    # Only take the positive frequencies
    idx = np.where(freq >= 0)
    amp_FDS = amp_FDS[idx]
    freq = freq[idx]

    return freq, amp_FDS

# Example usage
position_mm = np.linspace(125, 125.1, 100)  # position from 125 to 125.1 mm
TDS_amplitude = np.random.rand(100)  # example TDS amplitude data
xf, yf = thz_fft(position_mm, TDS_amplitude)

import matplotlib.pyplot as plt
plt.plot(xf, yf)
plt.xlabel('Frequency (THz)')
plt.ylabel('Amplitude')
plt.title('THz FDS FFT Spectrum')
plt.grid()
plt.show()
