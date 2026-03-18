// Lazy loading fallback for browsers that don't support loading="lazy"
(function () {
    if ("loading" in HTMLImageElement.prototype) return;

    var images = document.querySelectorAll('img[loading="lazy"]');
    if (!images.length) return;

    if ("IntersectionObserver" in window) {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    var img = entry.target;
                    img.src = img.dataset.src || img.src;
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: "200px" });

        images.forEach(function (img) { observer.observe(img); });
    }
})();

// GIF hover preview: show static first frame by default, animate on hover
(function () {
    var cards = document.querySelectorAll(".card");

    cards.forEach(function (card) {
        var canvas = card.querySelector(".gif-canvas");
        var img = card.querySelector(".gif-animated");
        if (!canvas || !img) return;

        var gifUrl = img.getAttribute("data-gif");
        var loaded = false;

        // Load the GIF in the hidden img, draw first frame to canvas
        img.onload = function () {
            loaded = true;
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            var ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0);
        };
        img.src = gifUrl;

        card.addEventListener("mouseenter", function () {
            if (!loaded) return;
            canvas.style.display = "none";
            img.style.display = "block";
        });

        card.addEventListener("mouseleave", function () {
            canvas.style.display = "block";
            img.style.display = "none";
        });
    });
})();
