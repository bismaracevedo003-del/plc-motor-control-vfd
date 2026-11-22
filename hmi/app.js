const STATES = ['STOPPED', 'STARTING', 'RUNNING', 'STOPPING', 'FAULTED'];

const elements = {
  state: document.getElementById('state'),
  frequency: document.getElementById('frequency'),
  current: document.getElementById('current'),
  fault: document.getElementById('fault'),
  ramps: document.getElementById('ramps'),
  setpoint: document.getElementById('setpoint'),
  setpointValue: document.getElementById('setpoint-value'),
};

async function api(path, body) {
  const response = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.json();
}

function render(snapshot) {
  elements.state.textContent = STATES[snapshot.State] || String(snapshot.State);
  elements.frequency.textContent = snapshot.ActualFrequency_Hz.toFixed(1);
  elements.current.textContent = snapshot.MotorCurrent_A.toFixed(2);
  elements.fault.textContent = snapshot.FaultName;
  elements.fault.className = snapshot.FaultCode ? 'fault-active' : '';
  elements.ramps.textContent = `${snapshot.AccelRate_Hz_s} Hz/s up · ${snapshot.DecelRate_Hz_s} Hz/s down`;
  if (document.activeElement !== elements.setpoint) {
    elements.setpoint.value = snapshot.SpeedSetpoint_Hz;
    elements.setpointValue.textContent = Number(snapshot.SpeedSetpoint_Hz).toFixed(0);
  }
}

async function refresh() {
  try {
    render(await api('/api/state'));
  } catch (error) {
    elements.state.textContent = 'OFFLINE';
  }
}

document.getElementById('start').onclick = () => api('/api/command', { command: 'START' });
document.getElementById('stop').onclick = () => api('/api/command', { command: 'STOP' });
document.getElementById('reset').onclick = () => api('/api/command', { command: 'RESET' });
elements.setpoint.oninput = (event) => {
  elements.setpointValue.textContent = event.target.value;
  api('/api/setpoint', { setpoint_hz: Number(event.target.value) });
};
document.querySelectorAll('[data-fault]').forEach((button) => {
  button.onclick = () => api('/api/fault', { fault: button.dataset.fault, active: true });
});

refresh();
setInterval(refresh, 300);
