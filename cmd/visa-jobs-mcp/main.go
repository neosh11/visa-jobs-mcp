package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/neosh11/visa-jobs-mcp/internal/mcp"
)

var version = "0.3.0"

func main() {
	showVersion := flag.Bool("version", false, "show version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Printf("visa-jobs-mcp-go %s\n", version)
		return
	}

	if err := mcp.Run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "mcp runtime error: %v\n", err)
		os.Exit(1)
	}
}
