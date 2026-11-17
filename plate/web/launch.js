if (location.protocol === "file:") {
  document.documentElement.classList.add("file-launch");
} else {
  import("./app.js").catch(error => {
    document.querySelector("#status").textContent = error.message;
  });
}
