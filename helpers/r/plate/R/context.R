plate_context <- function(path = Sys.getenv("PLATE_STYLE"),
                          defaults_path = system.file("extdata", "defaults.json", package = "plate")) {
  defaults <- jsonlite::fromJSON(defaults_path)
  if (nzchar(path)) {
    override <- jsonlite::fromJSON(path)
    defaults <- utils::modifyList(defaults, override, keep.null = TRUE)
  }
  offsets <- c(axis_title_pt = 0, tick_label_pt = -1, legend_title_pt = 0,
               legend_text_pt = -1, annotation_pt = 0, panel_label_pt = 1)
  for (token in names(offsets)) {
    if (is.null(defaults$style[[token]])) {
      defaults$style[[token]] <- max(defaults$style$font_min_pt,
                                     defaults$style$font_main_pt + offsets[[token]])
    }
  }
  defaults$colors <- unlist(defaults$colors)
  defaults
}
