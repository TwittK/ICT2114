function disableAddButton() {

  document.getElementById("deviceInfoData").value = ""; // Clear hidden device info
  addBtn.disabled = true;

  // Clear any validation messages
  const messageDiv = document.getElementById("cameraValidationMessage");
  messageDiv.textContent = "";
  messageDiv.classList.remove("text-success", "text-danger");
  
}

function validateCamera() {
  const ip = document.getElementById("cameraInput").value.trim();
  const messageDiv = document.getElementById("cameraValidationMessage");
  const addBtn = document.getElementById("addCameraBtn");
  const searchIcon = document.getElementById("searchIcon");

  messageDiv.textContent = "";
  addBtn.disabled = true;

  if (!ip) {
    messageDiv.textContent = "Please enter an IP address.";
    return;
  }
  var ipv4Regex = /^(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
  validate_ip = ipv4Regex.test(ip);
  if (!validate_ip) {
    messageDiv.textContent = "Please enter a valid IP address.";
    return;
  }

  // Set loading spinner
  searchIcon.innerHTML = `
    <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
    <span class="visually-hidden" role="status">Loading...</span>
  `;

  // Validate if IP of camera exists in NVR
  fetch("/check_ip", {
    method: "POST",
    headers: {
    "Content-Type": "application/json"
    },
    body: JSON.stringify({ ip: ip })
  })
  .then(response => response.json())
  .then(data => {
    if (data.valid) {
      messageDiv.textContent = "Camera found in NVR!";
      messageDiv.classList.remove("text-danger");
      messageDiv.classList.add("text-success");
      addBtn.disabled = false;

      // Store device_info of camera as JSON string in hidden input
      document.getElementById("deviceInfoData").value = JSON.stringify(data.device_info);

    } else {
      messageDiv.textContent = "Camera not found in NVR.";
      messageDiv.classList.remove("text-success");
      messageDiv.classList.add("text-danger");
      document.getElementById("deviceInfoData").value = "";
    }
  })
  .catch(error => {
    console.error("Error:", error);
    messageDiv.textContent = "Server error. Please try again.";
    messageDiv.classList.remove("text-success");
    messageDiv.classList.add("text-danger");
    document.getElementById("deviceInfoData").value = "";
  })
  .finally(() => {
    searchIcon.innerHTML = "🔍";
  });
}

function addNewCamera() {

  const ip = document.getElementById("cameraInput").value.trim();
  const deviceInfoRaw = document.getElementById("deviceInfoData").value;
  if (!ip || !deviceInfoRaw) {
    alert("Camera IP or device info missing.");
    return;
  }

  const deviceInfo = JSON.parse(deviceInfoRaw);
  fetch(`/index?add=1&lab={{ lab.lab_name }}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      ip: ip,
      device_info: deviceInfo
    })
  })
}

function registerListeners() {
  const cameraInput = document.getElementById("cameraInput");
  cameraInput.addEventListener("input", disableAddButton); // Disable add button on input change

  document.getElementById("validateCameraBtn").addEventListener("click", validateCamera); // Handle search button clicks

  document.getElementById("addCameraBtn").addEventListener("click", addNewCamera); // Handle add new camera clicks (after verifying IP address)
}


registerListeners();
