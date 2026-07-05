// Cloud RSVP frontend interactions.
document.addEventListener("DOMContentLoaded", () => {
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("photoUpload");
    const previewGrid = document.getElementById("previewGrid");

    if (!dropzone || !fileInput || !previewGrid) {
        return;
    }

    const renderPreviews = (files) => {
        previewGrid.innerHTML = "";

        Array.from(files)
            .filter((file) => file.type.startsWith("image/"))
            .forEach((file) => {
                const reader = new FileReader();

                reader.addEventListener("load", () => {
                    const image = document.createElement("img");
                    image.src = reader.result;
                    image.alt = file.name;
                    previewGrid.appendChild(image);
                });

                reader.readAsDataURL(file);
            });
    };

    fileInput.addEventListener("change", (event) => {
        renderPreviews(event.target.files);
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        fileInput.files = event.dataTransfer.files;
        renderPreviews(event.dataTransfer.files);
    });
});
