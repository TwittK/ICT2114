function disableAddButton() {
  const addBtn = document.getElementById("addCameraBtn");

  document.getElementById("deviceInfoData").value = ""; // Clear hidden device info
  addBtn.disabled = true;

  // Clear any validation messages
  const messageDiv = document.getElementById("cameraValidationMessage");
  messageDiv.textContent = "";
  messageDiv.classList.remove("text-success", "text-danger");
  
}

function validateIPv4(ip) {
  const parts = ip.split(".");
  if (parts.length !== 4) return false; // Contains 4 parts

  // Check that each part contains 3 digits and is between 0 to 255
  return parts.every(part => {
    const n = Number(part);
    return /^\d{1,3}$/.test(part) && n >= 0 && n <= 255;
  });
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
  validateIPResults = validateIPv4(ip);
  if (!validateIPResults) {
    messageDiv.textContent = "Please enter a valid IP address.";
    return;
  }

  // Set loading spinner
  searchIcon.innerHTML = `
    <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
    <span class="visually-hidden" role="status">Loading...</span>
  `;

  document.getElementById("deviceInfoData").value = ""; // Clear hidden device info
  
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
      setTimeout(function() {
        messageDiv.textContent = '';
      }, 7000); 
      messageDiv.classList.remove("text-success");
      messageDiv.classList.add("text-danger");
    }
  })
  .catch(error => {
    console.error("Error:", error);
    messageDiv.textContent = "Server error. Please try again.";
    setTimeout(function() {
      messageDiv.textContent = '';
    }, 7000); 
    messageDiv.classList.remove("text-success");
    messageDiv.classList.add("text-danger");
  })
  .finally(() => {
    searchIcon.innerHTML = "🔍";
  });
}

function addNewCamera() {
  const ip = document.getElementById("cameraInput").value.trim();
  const deviceInfoRaw = document.getElementById("deviceInfoData").value;
  const labName = document.getElementById("selectedLabName").value;
  
  if (!ip || !deviceInfoRaw) {
    alert("Camera IP or device info missing.");
    return;
  }

  if (!labName) {
    alert("Lab name is missing.");
    return;
  }

  const deviceInfo = JSON.parse(deviceInfoRaw);
  
  fetch(`/add_camera`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      ip: ip,
      device_info: deviceInfo,
      lab_name: labName
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert("Camera added successfully!");
      location.reload(); // Reload the page to show the new camera
    } else {
      alert("Failed to add camera: " + data.message);
    }
  })
  .catch(error => {
    console.error("Error:", error);
    alert("Error adding camera. Please try again.");
  });
}

function registerListeners() {
  const cameraInput = document.getElementById("cameraInput");
  cameraInput.addEventListener("input", disableAddButton);

  document.getElementById("validateCameraBtn").addEventListener("click", validateCamera);
  document.getElementById("addCameraBtn").addEventListener("click", addNewCamera);

  // Handle modal show event to capture lab name
  const addCameraModal = document.getElementById('addCameraModal');
  addCameraModal.addEventListener('show.bs.modal', function (event) {
    // Button that triggered the modal
    const button = event.relatedTarget;
    // Extract lab name from data-* attributes
    const labName = button.getAttribute('data-lab-name');
    
    // Update the modal's title to show lab name
    const modalTitle = addCameraModal.querySelector('#addCameraModalLabel');
    const selectedLabInput = addCameraModal.querySelector('#selectedLabName');
    
    if (modalTitle) {
      modalTitle.textContent = `Add New Camera to ${labName}`;
    }
    
    if (selectedLabInput) {
      selectedLabInput.value = labName;
    }
    
    // Reset form when modal opens
    document.getElementById("cameraInput").value = "";
    document.getElementById("cameraValidationMessage").textContent = "";
    document.getElementById("deviceInfoData").value = "";
    document.getElementById("addCameraBtn").disabled = true;
  });
}

registerListeners();