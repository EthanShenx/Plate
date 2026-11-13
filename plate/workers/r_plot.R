args <- commandArgs(trailingOnly = TRUE)
script <- args[[1]]
output <- args[[2]]
metadata <- args[[3]]
helper <- args[[4]]
source(file.path(helper, "R", "context.R"), local = TRUE)
plate <- plate_context(defaults_path = file.path(helper, "inst", "extdata", "defaults.json"))
s <- plate$style
suppressPackageStartupMessages(library(ggplot2))

# ggplot2 multiplies linewidth by .pt; the Cairo device uses 1/96 inch per lwd.
lwd <- function(pt) pt * 96 / 72
linewidth <- function(pt) lwd(pt) / ggplot2::.pt
text_mm <- function(pt) pt / ggplot2::.pt
axis_line <- element_line(linewidth = linewidth(s$line_axis_pt))
background <- if (s$background == "white") "white" else "transparent"
family <- s$font_family
if (plate$inject) {
  matched <- systemfonts::font_info(family)$family[[1]]
  if (!identical(tolower(matched), tolower(family))) {
    warning(sprintf("Font %s resolves to %s in systemfonts.", family, matched))
  }
  elements <- list(
    axis.title = element_text(size = s$axis_title_pt),
    axis.text = element_text(size = s$tick_label_pt, colour = "black"),
    legend.title = element_text(size = s$legend_title_pt),
    legend.text = element_text(size = s$legend_text_pt),
    axis.ticks = element_line(linewidth = linewidth(s$tick_width_pt)),
    axis.ticks.length = grid::unit(s$tick_length_pt * if (s$tick_direction == "in") -1 else 1, "bigpts"),
    axis.line = if (s$spines == "left-bottom") axis_line else element_blank(),
    panel.border = if (s$spines == "all")
      element_rect(colour = "black", fill = NA, linewidth = linewidth(s$line_axis_pt)) else element_blank(),
    panel.grid.minor = element_blank(),
    panel.grid.major = if (s$grid == "major")
      element_line(colour = "#dddddd", linewidth = linewidth(s$line_axis_pt)) else element_blank(),
    panel.background = element_rect(fill = background, colour = NA),
    plot.background = element_rect(fill = background, colour = NA),
    legend.key = element_blank(), legend.background = element_blank(),
    plot.title = element_text(size = s$font_main_pt), strip.text = element_text(size = s$tick_label_pt)
  )
  theme_set(theme_minimal(base_size = s$font_main_pt, base_family = family) + do.call(theme, elements))
  for (geom in c("line", "path", "segment", "step", "hline", "vline", "abline",
                 "smooth", "density", "contour", "linerange", "errorbar", "pointrange",
                 "polygon", "rect", "bar", "col", "boxplot", "violin")) {
    update_geom_defaults(geom, list(linewidth = linewidth(s$line_data_pt)))
  }
  update_geom_defaults("point", list(size = text_mm(s$marker_size_pt)))
  for (geom in c("text", "label")) {
    update_geom_defaults(geom, list(size = text_mm(s$annotation_pt), family = family))
  }
  # The ggplot2 discrete options accept palette vectors and preserve normal scale arguments.
  options(ggplot2.discrete.colour = plate$palette, ggplot2.discrete.fill = plate$palette)
}

size <- plate$size_mm / 25.4
grDevices::cairo_pdf(output, width = size[[1]], height = size[[2]],
                     pointsize = if (plate$inject) s$font_main_pt else 12,
                     family = if (plate$inject) family else "sans",
                     bg = if (plate$inject) background else "white")
device <- grDevices::dev.cur()
if (plate$inject) {
  line_inches <- graphics::par("csi") * graphics::par("mex")
  graphics::par(family = family, col = plate$palette[[1]], fg = "#000000",
                lwd = lwd(s$line_data_pt), cex = 1, cex.axis = s$tick_label_pt / s$font_main_pt,
                cex.lab = s$axis_title_pt / s$font_main_pt,
                tcl = s$tick_length_pt / (72 * line_inches) * if (s$tick_direction == "in") 1 else -1,
                bty = switch(s$spines, all = "o", `left-bottom` = "l", none = "n"))
}
env <- new.env(parent = globalenv())
env$plate <- plate
if (plate$inject) {
  env$plot <- function(x, y = NULL, ..., axes = TRUE, frame.plot = axes,
                       xlab = NULL, ylab = NULL) {
    labels <- list(xlab = xlab, ylab = ylab)
    if (is.null(xlab)) labels$xlab <- deparse(substitute(x), nlines = 1)
    if (is.null(ylab) && !missing(y)) labels$ylab <- deparse(substitute(y), nlines = 1)
    if (is.object(x)) {
      return(do.call(graphics::plot, c(list(x = x, y = y, ..., axes = axes,
                                           frame.plot = frame.plot), labels)))
    }
    do.call(graphics::plot.default, c(list(x = x, y = y, ..., axes = FALSE,
                                           frame.plot = FALSE), labels))
    if (s$grid == "major") graphics::grid(lwd = lwd_axis)
    if (axes) {
      env$axis(1)
      env$axis(2)
    }
    if (frame.plot && s$spines != "none") env$box()
  }
  env$axis <- function(..., lwd = lwd_axis, lwd.ticks = lwd_tick) {
    graphics::axis(..., lwd = lwd, lwd.ticks = lwd.ticks)
  }
  env$box <- function(..., lwd = lwd_axis) graphics::box(..., lwd = lwd)
  env$text <- function(..., cex = annotation_scale) graphics::text(..., cex = cex)
  lwd_axis <- lwd(s$line_axis_pt)
  lwd_tick <- lwd(s$tick_width_pt)
  annotation_scale <- s$annotation_pt / s$font_main_pt
}
if (!is.null(plate$fixed_axes)) {
  bounds <- plate$fixed_axes
  graphics::par(plt = bounds[c(1, 3, 2, 4)])
}

measure_gtable <- function(table) {
  grid::grid.draw(table)
  grid::grid.force()
  entries <- grid::grid.ls(viewports = TRUE, grobs = FALSE, print = FALSE)$name
  boxes <- lapply(grep("^panel(-[0-9]+)*\\.[0-9]+-", unique(entries), value = TRUE), function(name) {
    tryCatch({
      grid::seekViewport(name)
      a <- grid::deviceLoc(grid::unit(0, "npc"), grid::unit(0, "npc"), valueOnly = TRUE)
      b <- grid::deviceLoc(grid::unit(1, "npc"), grid::unit(1, "npc"), valueOnly = TRUE)
      c(a$x / size[[1]], a$y / size[[2]], b$x / size[[1]], b$y / size[[2]])
    }, error = function(e) NULL)
  })
  boxes <- Filter(Negate(is.null), boxes)
  if (!length(boxes)) return(NULL)
  m <- do.call(rbind, boxes)
  c(min(m[, 1]), min(m[, 2]), max(m[, 3]), max(m[, 4]))
}

align_gtable <- function(table, natural, target) {
  left <- max(0, target[[1]] - natural[[1]]) * size[[1]]
  right <- max(0, natural[[3]] - target[[3]]) * size[[1]]
  top <- max(0, natural[[4]] - target[[4]]) * size[[2]]
  bottom <- max(0, target[[2]] - natural[[2]]) * size[[2]]
  table <- gtable::gtable_add_cols(table, grid::unit(left, "inches"), pos = 0)
  table <- gtable::gtable_add_cols(table, grid::unit(right, "inches"))
  table <- gtable::gtable_add_rows(table, grid::unit(top, "inches"), pos = 0)
  gtable::gtable_add_rows(table, grid::unit(bottom, "inches"))
}

axes <- NULL
tryCatch({
  last <- NULL
  for (expression in parse(file = script, keep.source = TRUE)) {
    value <- withVisible(eval(expression, envir = env))
    if (value$visible && inherits(value$value, "ggplot")) last <- value$value
  }
  candidate <- get0("p", envir = env, inherits = FALSE)
  plot <- if (inherits(candidate, "ggplot")) candidate else last
  if (!is.null(plot)) {
    grid::grid.newpage()
    table <- if (inherits(plot, "patchwork")) patchwork::patchworkGrob(plot) else ggplotGrob(plot)
    target <- plate$fixed_axes
    if (!is.null(target)) {
      # Measure with an independent recording device. The output device receives
      # one draw, and the added fixed gutters only shrink the flexible panel tracks.
      scratch <- tempfile(fileext = ".pdf")
      grDevices::cairo_pdf(scratch, width = size[[1]], height = size[[2]],
                           family = if (plate$inject) family else "sans")
      natural <- tryCatch(measure_gtable(table), finally = {
        grDevices::dev.off()
        unlink(scratch)
      })
      if (!is.null(natural)) table <- align_gtable(table, natural, target)
    }
    axes <- measure_gtable(table)
  } else {
    p <- graphics::par("plt")
    axes <- p[c(1, 3, 2, 4)]
  }
}, error = function(error) {
  message("R traceback:")
  for (call in sys.calls()) message(paste(deparse(call, width.cutoff = 120L), collapse = " "))
  stop(error)
}, finally = {
  if (device %in% grDevices::dev.list()) invisible(grDevices::dev.off(device))
})
jsonlite::write_json(list(axes = axes), metadata, auto_unbox = TRUE, digits = 12)
