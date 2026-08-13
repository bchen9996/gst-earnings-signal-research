#!/usr/bin/env Rscript
# Independent CR2 / Satterthwaite reference for the HYP-01 synthetic fixtures.
#
# NOT PRODUCTION CODE. SYNTHETIC DATA ONLY. NO RESEARCH ARTIFACT IS READ.
#
# This script is the INDEPENDENT side of the validation. It must not import,
# mirror, or re-derive anything from the Python implementation it is checking.
# It reads the exported fixture file, fits the same OLS specification, and asks
# clubSandwich -- an independently maintained package written by other authors
# -- for the CR2 covariance and the Satterthwaite coefficient test.
#
# It deliberately does NOT regenerate fixtures. If the interchange file is
# missing, malformed, reordered, or fails its digest, this script stops.
#
# Usage:
#   Rscript cr2_reference.R --fixtures <in.json> --out <out.json> [--expect-sha256 <hex>]

suppressWarnings(suppressMessages({
  library(jsonlite)
  library(clubSandwich)
  library(digest)
}))

args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(flag, required = TRUE) {
  i <- match(flag, args)
  if (is.na(i) || i == length(args)) {
    if (required) stop(sprintf("missing required argument: %s", flag), call. = FALSE)
    return(NULL)
  }
  args[[i + 1L]]
}
fixtures_path <- get_arg("--fixtures")
out_path      <- get_arg("--out")
expect_sha    <- get_arg("--expect-sha256", required = FALSE)

# --------------------------------------------------------------------------
# Canonical rendering. Must match the Python exporter exactly.
# %.17g round-trips an IEEE-754 double and is specified identically in C, so
# sprintf here and format() there agree.
# --------------------------------------------------------------------------
FLOAT_FORMAT  <- "%.17g"
MISSING_TOKEN <- "NA"

fmt_num <- function(v) {
  ifelse(is.na(v), MISSING_TOKEN, sprintf(FLOAT_FORMAT, v))
}

# Numeric OUTPUT is emitted as %.17g strings, not as JSON numbers.
#
# jsonlite writes doubles with about 15 significant digits, which silently
# discards the last 1-2 ulp. That is far inside the preregistered tolerances,
# but it would mean the reported discrepancies partly measured the JSON writer
# rather than the two implementations. %.17g round-trips an IEEE-754 double
# exactly, so the comparison measures the computation.
num17 <- function(v) {
  if (is.null(v) || length(v) == 0) return(list())
  as.list(vapply(as.numeric(v),
                 function(z) if (is.na(z)) NA_character_ else sprintf(FLOAT_FORMAT, z),
                 character(1)))
}
scalar17 <- function(v) {
  if (is.null(v) || length(v) == 0 || is.na(v)) return(NA_character_)
  sprintf(FLOAT_FORMAT, as.numeric(v))
}

canonical_string <- function(fx) {
  # X arrives row-major; flatten in the same order the exporter used.
  Xflat <- as.vector(t(fx$X))
  paste(
    fx$fixture_id,
    format(fx$n_obs, scientific = FALSE),
    format(fx$n_params, scientific = FALSE),
    paste(fx$coefficient_names, collapse = ","),
    fx$target_coefficient,
    paste(fx$cluster_labels, collapse = ","),
    paste(fmt_num(fx$y), collapse = ","),
    paste(fmt_num(Xflat), collapse = ","),
    sep = "|"
  )
}

# --------------------------------------------------------------------------
# Read and validate the interchange file. Reject anything malformed.
# --------------------------------------------------------------------------
if (!file.exists(fixtures_path)) stop("fixture file not found: ", fixtures_path, call. = FALSE)

file_sha <- digest(file = fixtures_path, algo = "sha256")
raw_txt  <- readChar(fixtures_path, file.info(fixtures_path)$size, useBytes = TRUE)
# Hash the LF-normalised bytes too, so a CRLF checkout is not a false mismatch.
lf_sha <- digest(gsub("\r\n", "\n", raw_txt, fixed = TRUE), algo = "sha256", serialize = FALSE)

if (!is.null(expect_sha) && !(expect_sha %in% c(file_sha, lf_sha))) {
  stop(sprintf("fixture file digest mismatch: expected %s, got raw=%s lf=%s",
               expect_sha, file_sha, lf_sha), call. = FALSE)
}

doc <- fromJSON(fixtures_path, simplifyVector = TRUE, simplifyDataFrame = FALSE)
if (!identical(doc$schema, "GST_HYP01_R_REFERENCE_FIXTURE_INTERCHANGE_v1")) {
  stop("unexpected interchange schema: ", doc$schema, call. = FALSE)
}
if (length(doc$fixtures) != doc$fixture_count) {
  stop("fixture_count disagrees with the number of fixtures present", call. = FALSE)
}
ids <- vapply(doc$fixtures, function(f) f$fixture_id, character(1))
if (anyDuplicated(ids)) stop("duplicate fixture identifiers", call. = FALSE)

# --------------------------------------------------------------------------
# Specification, stated explicitly. Nothing here is left to a default.
# --------------------------------------------------------------------------
SPEC <- list(
  intercept_handling = paste(
    "The design matrix carries its OWN intercept column (all ones) as column 1.",
    "The model is fitted with `y ~ 0 + .` so R does NOT add a second intercept.",
    "Coefficient order therefore matches the exported coefficient_names exactly."),
  coefficient_ordering = "as exported: column j of X <-> coefficient_names[j], no reordering",
  cluster_ordering = paste(
    "cluster labels are used in the exported row order and converted with",
    "factor(labels, levels = unique(labels)) so factor levels follow first",
    "appearance rather than locale-dependent alphabetical sorting"),
  target_coefficient = "coefficient_names[target_index_0based + 1] (the slope on x)",
  null_value = doc$null_value,
  confidence_level = doc$confidence_level,
  missing_value_behaviour = paste(
    "na.action = na.fail. R's default (na.omit) would SILENTLY DROP the row",
    "with a missing outcome and return a number, which would be a false",
    "agreement. Failing is the correct reference behaviour to compare against."),
  cr2_call = "clubSandwich::vcovCR(fit, cluster = <factor>, type = 'CR2')",
  satterthwaite_call = "clubSandwich::coef_test(fit, vcov = <CR2>, test = 'Satterthwaite')",
  conf_int_call = "clubSandwich::conf_int(fit, vcov = <CR2>, test = 'Satterthwaite', level = 0.95)",
  leverage_adjustment = paste(
    "CR2 is the bias-reduced linearisation of Bell & McCaffrey / Pustejovsky &",
    "Tipton: A_g is the symmetric inverse square root of (I - H_gg) under the",
    "identity working model. clubSandwich computes this internally; this script",
    "does not supply or override the adjustment matrices."),
  working_model_target = paste(
    "target is left NULL, which for an unweighted lm is the identity working",
    "model -- the same homoskedastic-independent working model the Python side",
    "assumes. The resolved defaults are recorded in `reference_defaults`."),
  matrix_tolerance = paste(
    "clubSandwich's own internal inversion tolerance is used and is NOT",
    "overridden here. The Python side clips eigenvalues of (I - H_gg) at 1e-12.",
    "These are different mechanisms; any disagreement they cause is a finding,",
    "not something to be tuned away.")
)

# Record clubSandwich's resolved argument defaults rather than assuming them.
reference_defaults <- tryCatch({
  f <- formals(getS3method("vcovCR", "lm"))
  lapply(f[intersect(names(f), c("type", "target", "inverse_var", "form"))],
         function(v) paste(deparse(v), collapse = ""))
}, error = function(e) list(error = conditionMessage(e)))

# --------------------------------------------------------------------------
# Per-fixture reference computation.
# --------------------------------------------------------------------------
run_fixture <- function(fx) {
  target_idx <- doc$target_index_0based + 1L
  cnames <- fx$coefficient_names
  target <- cnames[[target_idx]]

  # ---- integrity of THIS fixture, recomputed independently in R ----
  recomputed <- digest(canonical_string(fx), algo = "sha256", serialize = FALSE)
  digest_ok <- identical(recomputed, fx$canonical_sha256)

  y <- as.numeric(fx$y)
  Xm <- fx$X
  if (is.list(Xm)) Xm <- do.call(rbind, lapply(Xm, function(r) as.numeric(unlist(r))))
  Xm <- matrix(as.numeric(Xm), nrow = fx$n_obs, ncol = fx$n_params, byrow = FALSE)
  # fromJSON gives a row-major list of rows; rbind above already yields rows.
  if (is.list(fx$X)) {
    Xm <- do.call(rbind, lapply(fx$X, function(r) as.numeric(unlist(r))))
  }
  colnames(Xm) <- cnames

  base <- list(
    fixture_id = fx$fixture_id,
    n_obs = fx$n_obs, n_params = fx$n_params, n_clusters = fx$n_clusters,
    target_coefficient = target,
    canonical_digest_recomputed = recomputed,
    canonical_digest_matches_export = digest_ok,
    dimensions_agree = (length(y) == fx$n_obs &&
                        nrow(Xm) == fx$n_obs && ncol(Xm) == fx$n_params &&
                        length(fx$cluster_labels) == fx$n_obs)
  )
  if (!digest_ok) {
    return(c(base, list(status = "INTERCHANGE_DIGEST_MISMATCH",
                        message = "R recomputed a different canonical digest")))
  }
  if (!base$dimensions_agree) {
    return(c(base, list(status = "INTERCHANGE_DIMENSION_MISMATCH",
                        message = "declared dimensions do not match the payload")))
  }
  # NOTE: every path below assigns to `res` and falls through to c(base, res).
  # An earlier revision used return() inside tryCatch(), which exits the whole
  # function and silently dropped the base fields -- making the integrity
  # digest look like a mismatch on exactly the fixtures that refused.

  cl <- factor(unlist(fx$cluster_labels), levels = unique(unlist(fx$cluster_labels)))
  df <- data.frame(.y = y, Xm, check.names = FALSE)

  # Warnings are COLLECTED, not treated as failure. R warns "essentially
  # perfect fit" on a degenerate fixture but still returns numbers; aborting on
  # the warning would hide what the reference actually does, and the difference
  # between warn-and-continue and refuse is precisely what must be reported.
  warnings_seen <- character(0)

  res <- withCallingHandlers(
    tryCatch({
      fit <- lm(.y ~ 0 + ., data = df, na.action = na.fail)

      aliased <- names(which(is.na(coef(fit))))
      if (length(aliased) > 0) {
        list(status = "REFERENCE_REFUSED",
             refusal_stage = "lm_fit",
             refusal_reason = "RANK_DEFICIENT_ALIASED_COEFFICIENT",
             message = paste("lm() could not estimate:", paste(aliased, collapse = ", ")))
      } else {
        V <- vcovCR(fit, cluster = cl, type = "CR2")
        ct <- coef_test(fit, vcov = V, test = "Satterthwaite", coefs = "All")
        ci <- tryCatch(
          conf_int(fit, vcov = V, test = "Satterthwaite", level = doc$confidence_level,
                   coefs = "All"),
          error = function(e) NULL)

        # Sensitivity on the one argument whose resolved default is not visible
        # from formals(): does the identity-working-model branch matter here?
        iv_delta <- tryCatch({
          Vt <- as.matrix(vcovCR(fit, cluster = cl, type = "CR2", inverse_var = TRUE))
          Vf <- as.matrix(vcovCR(fit, cluster = cl, type = "CR2", inverse_var = FALSE))
          max(abs(Vt - Vf))
        }, error = function(e) NA_real_)

        Vm <- as.matrix(V)
        row <- match(target, rownames(ct))
        if (is.na(row)) row <- target_idx

        out <- list(
          status = "COMPUTED",
          numeric_encoding = "%.17g strings; parse with float()/as.numeric()",
          coefficients = num17(coef(fit)),
          coefficient_names = names(coef(fit)),
          cr2_covariance = lapply(seq_len(nrow(Vm)), function(i) num17(Vm[i, ])),
          target_variance = scalar17(Vm[target_idx, target_idx]),
          target_estimate = scalar17(coef(fit)[[target_idx]]),
          standard_error = scalar17(ct$SE[row]),
          t_statistic = scalar17(ct$tstat[row]),
          satterthwaite_df = scalar17(ct$df_Satt[row]),
          p_value = scalar17(ct$p_Satt[row]),
          residual_df = as.numeric(fit$df.residual),
          inverse_var_max_abs_difference = scalar17(iv_delta)
        )
        if (!is.null(ci)) {
          r2 <- match(target, rownames(ci))
          if (is.na(r2)) r2 <- target_idx
          out$conf_int_low <- scalar17(ci$CI_L[r2])
          out$conf_int_high <- scalar17(ci$CI_U[r2])
          out$conf_int_defined <- TRUE
        } else {
          out$conf_int_defined <- FALSE
        }
        out
      }
    }, error = function(e) {
      list(status = "REFERENCE_REFUSED",
           refusal_stage = "exception",
           refusal_reason = "R_ERROR",
           message = conditionMessage(e))
    }),
    warning = function(w) {
      warnings_seen <<- c(warnings_seen, conditionMessage(w))
      invokeRestart("muffleWarning")
    })

  res$reference_warnings <- as.list(unique(warnings_seen))
  res$reference_warning_count <- length(warnings_seen)
  res$reference_warned <- length(warnings_seen) > 0
  c(base, res)
}

results <- lapply(doc$fixtures, run_fixture)
names(results) <- ids

# --------------------------------------------------------------------------
# Assemble output.
# --------------------------------------------------------------------------
si <- sessionInfo()
out_doc <- list(
  artifact = "GST HYP-01 independent R reference (CR2 + Satterthwaite)",
  schema = "GST_HYP01_R_REFERENCE_OUTPUT_v1",
  synthetic_data_only = TRUE,
  research_artifact_read = FALSE,
  reference_package = "clubSandwich",
  reference_is_independently_maintained = TRUE,
  reference_written_for_this_study = FALSE,
  fixture_file = basename(fixtures_path),
  fixture_file_sha256_raw = file_sha,
  fixture_file_sha256_lf = lf_sha,
  fixture_source_runner_sha256 = doc$source_of_truth$runner_sha256,
  fixtures_regenerated_in_r = FALSE,
  specification = SPEC,
  reference_defaults = reference_defaults,
  environment = list(
    r_version = paste(R.version$major, R.version$minor, sep = "."),
    r_version_string = R.version.string,
    platform = R.version$platform,
    clubSandwich = as.character(packageVersion("clubSandwich")),
    jsonlite = as.character(packageVersion("jsonlite")),
    digest = as.character(packageVersion("digest")),
    sandwich = tryCatch(as.character(packageVersion("sandwich")), error = function(e) NA_character_),
    zoo = tryCatch(as.character(packageVersion("zoo")), error = function(e) NA_character_)
  ),
  results = results
)

writeLines(toJSON(out_doc, auto_unbox = TRUE, digits = NA, null = "null",
                  na = "null", pretty = TRUE), out_path)
cat("wrote", out_path, "\n")
cat("  fixtures processed:", length(results), "\n")
cat("  computed:", sum(vapply(results, function(r) identical(r$status, "COMPUTED"), logical(1))), "\n")
cat("  reference refused:", sum(vapply(results, function(r) identical(r$status, "REFERENCE_REFUSED"), logical(1))), "\n")
