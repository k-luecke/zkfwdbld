use std::io::{self, Read};

fn main() {
    let mut input = Vec::new();
    io::stdin().read_to_end(&mut input).expect("read stdin");
    let output = zkfwdbld::process_json_request(&input);
    println!("{}", String::from_utf8(output).expect("utf8 response"));
}
