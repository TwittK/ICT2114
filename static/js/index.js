function updateDateTime() {
  const now = new Date();
  
  // Format time (11:13 PM)
  const timeOptions = { 
    hour: 'numeric', 
    minute: '2-digit', 
    hour12: true 
  };
  const timeString = now.toLocaleTimeString('en-US', timeOptions);
  
  // Format date (Monday, 6 February, 2023)
  const dateOptions = { 
    weekday: 'long', 
    day: 'numeric', 
    month: 'long', 
    year: 'numeric' 
  };
  const dateString = now.toLocaleDateString('en-US', dateOptions);
  
  document.getElementById('current-time').textContent = timeString;
  document.getElementById('current-date').textContent = dateString;
}

// Update immediately and then every minute
updateDateTime();
setInterval(updateDateTime, 60000);